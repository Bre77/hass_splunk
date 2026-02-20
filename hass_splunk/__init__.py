import asyncio
import json
from collections import deque
from typing import Any, Deque, Dict, Optional, Union

import aiohttp

SPLUNK_PAYLOAD_LIMIT = 512000  # 500KB, Actual limit is 512KB/880MB depending on version.


class SplunkPayloadError(aiohttp.ClientPayloadError):
    def __init__(self, code: int, message: str, status: int) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(self.message)


class hass_splunk:
    """Splunk HTTP Event Collector interface for Home Assistant"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        host: str,
        port: int = 8088,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        endpoint: str = "collector/event",
        timeout: Union[int, float] = 60,
    ) -> None:
        self.session = session
        self.url = f"{['http', 'https'][use_ssl]}://{host}:{port}/services/{endpoint}"
        self.verify_ssl = verify_ssl
        self.headers = {"Authorization": f"Splunk {token}"}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.batch: Deque[str] = deque()
        self.lock = asyncio.Lock()

    async def queue(self, payload: Any, send: bool = True) -> Optional[bool]:
        if not isinstance(payload, str):
            payload = json.dumps(payload)

        self.batch.append(payload)
        if send:
            return await self.send()
        return None

    async def send(self) -> bool:
        if self.lock.locked():
            return False
        async with self.lock:
            # Run until there are no new events to sent
            while self.batch:
                size = len(self.batch[0])
                events: Deque[str] = deque()
                # Do Until loop to get events until maximum payload size or no more events
                # Ensures at least 1 event is always sent even if it exceeds the size limit
                while True:
                    # Add first event
                    events.append(self.batch.popleft())
                    # Stop if no more events
                    if not self.batch:
                        break
                    # Add size of next event
                    size += len(self.batch[0])
                    # Stop if next event exceeds limit
                    if size > SPLUNK_PAYLOAD_LIMIT:
                        break
                # Send the selected events
                try:
                    async with self.session.post(
                        self.url,
                        data="\n".join(events),
                        ssl=self.verify_ssl,
                        headers=self.headers,
                        timeout=self.timeout
                    ) as resp:
                        reply = await resp.json()
                        if not isinstance(reply, dict):
                            resp.raise_for_status()
                            raise aiohttp.ClientResponseError(
                                request_info=resp.request_info,
                                history=resp.history,
                                status=resp.status,
                                message="Invalid JSON response from Splunk HEC",
                                headers=resp.headers,
                            )
                        typed_reply = reply
                        if "code" not in typed_reply or "text" not in typed_reply:
                            resp.raise_for_status()
                        if typed_reply["code"] != 0:
                            if resp.status in [500, 503]:  # Only retry on server errors
                                self.batch = events + self.batch
                            raise SplunkPayloadError(
                                code=int(typed_reply["code"]),
                                message=str(typed_reply["text"]),
                                status=resp.status,
                            )

                except (
                    aiohttp.ClientConnectionError,
                    aiohttp.ClientResponseError,
                    asyncio.TimeoutError,
                ) as error:
                    # Requeue failed events before raising the error
                    self.batch = events + self.batch
                    raise error

        return True

    async def check(
        self,
        connectivity: bool = True,
        token: bool = True,
        busy: bool = True,
    ) -> Optional[bool]:
        try:
            async with self.session.post(
                self.url,
                ssl=self.verify_ssl,
                headers=self.headers,
                timeout=self.timeout,
            ) as resp:
                reply = await resp.json()
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            return not connectivity
        except Exception:
            return False
        if not isinstance(reply, dict):
            return False
        status_map: Dict[int, Optional[bool]] = {
            0: True,  # Success
            1: not token,  # Token disabled
            2: not token,  # Token is required
            3: not token,  # Invalid authorization
            4: not token,  # Invalid token
            5: True,  # No data - Expected
            6: True,  # Invalid data format
            7: True,  # Incorrect index
            8: False,  # Internal server error
            9: not busy,  # Server is busy
            10: False,  # Data channel is missing
            11: False,  # Invalid data channel
            12: None,  # Event field is required
            13: None,  # Event field cannot be blank
            14: None,  # ACK is disabled
            15: None,  # Error in handling indexed fields
            16: None,  # Query string authorization is not enabled
        }
        code = reply.get("code")
        if not isinstance(code, int):
            return False
        return status_map.get(code, False)

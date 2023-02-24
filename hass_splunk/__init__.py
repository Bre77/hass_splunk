import aiohttp
import asyncio
import json
from collections import deque

SPLUNK_PAYLOAD_LIMIT = 512000  # 500KB, Actual limit is 512KB/880MB depending on version.

class SplunkPayloadError(aiohttp.ClientPayloadError):
    def __init__(self,code,message,status):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(self.message)

class hass_splunk:
    """Splunk HTTP Event Collector interface for Home Assistant"""

    def __init__(
        self,
        session,
        token,
        host,
        port=8088,
        use_ssl=True,
        verify_ssl=True,
        endpoint="collector/event",
        timeout=60,
    ):
        self.session = session
        self.url = f"{['http','https'][use_ssl]}://{host}:{port}/services/{endpoint}"
        self.verify_ssl = verify_ssl
        self.headers = {"Authorization": f"Splunk {token}"}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.batch = deque()
        self.lock = asyncio.Lock()

    async def queue(self, payload, send=True):
        if not isinstance(payload, str):
            payload = json.dumps(payload)

        self.batch.append(payload)
        if send:
            return await self.send()

    async def send(self):
        if self.lock.locked():
            return False
        async with self.lock:
            # Run until there are no new events to sent
            while self.batch:
                size = len(self.batch[0])
                events = deque()
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
                        if "code" not in reply or "text" not in reply:
                            resp.raise_for_status()
                        if reply["code"] != 0:
                            if resp.status in [500, 503]: # Only retry on server errors
                                self.batch = events + self.batch
                            raise SplunkPayloadError(code=reply["code"],message=reply["text"],status=resp.status)
                        
                except (aiohttp.ClientConnectionError,aiohttp.ClientResponseError,asyncio.TimeoutError) as error:
                    # Requeue failed events before raising the error
                    self.batch = events + self.batch
                    raise error
                
        return True

    async def check(self, connectivity=True, token=True, busy=True):
        try:
            async with self.session.post(
                self.url,
                ssl=self.verify_ssl,
                headers=self.headers,
                timeout=self.timeout,
            ) as resp:
                reply = await resp.json()
        except (aiohttp.ClientConnectionError,asyncio.TimeoutError):
            return not connectivity
        except Exception:
            return False
        return {
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
        }.get(reply["code"], False)

"""Tests for the bounded, drop-oldest event queue in hass_splunk.

No third-party test runner is required beyond ``aiohttp`` (which the library
already depends on). Run directly with::

    python -m unittest tests.test_queue_bound

or via pytest if available.
"""

import asyncio
import unittest
from collections import deque
from contextlib import asynccontextmanager
from typing import List

from hass_splunk import DEFAULT_MAX_QUEUE, hass_splunk


class _FakeResponse:
    """Minimal stand-in for an aiohttp response with a fixed JSON body."""

    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self._body = body
        self.request_info = None
        self.history = ()
        self.headers = {}

    async def json(self):
        return self._body

    def raise_for_status(self):
        return None


class _FakeSession:
    """Records POST bodies and replies with a scripted status/JSON code."""

    def __init__(self, status: int, code: int) -> None:
        self.status = status
        self.code = code
        self.sent_bodies: List[str] = []

    @asynccontextmanager
    async def post(self, url, data=None, **kwargs):
        if data is not None:
            self.sent_bodies.append(data)
        yield _FakeResponse(self.status, {"code": self.code, "text": "scripted"})


def _client(session, max_queue: int) -> hass_splunk:
    return hass_splunk(session, token="t", host="h", max_queue=max_queue)


class QueueBoundTests(unittest.TestCase):
    def test_default_cap_applied(self):
        client = _client(_FakeSession(200, 0), DEFAULT_MAX_QUEUE)
        self.assertEqual(client.batch.maxlen, DEFAULT_MAX_QUEUE)

    def test_queue_never_exceeds_cap(self):
        async def run():
            client = _client(_FakeSession(200, 0), max_queue=10)
            for i in range(1000):
                await client.queue(f"event-{i}", send=False)
            return client

        client = asyncio.run(run())
        self.assertEqual(len(client.batch), 10)
        self.assertLessEqual(len(client.batch), client.max_queue)
        # Drop-oldest: only the newest 10 events survive, in order.
        self.assertEqual(
            list(client.batch),
            [f"event-{i}" for i in range(990, 1000)],
        )

    def test_requeue_preserves_order_and_bound(self):
        client = _client(_FakeSession(200, 0), max_queue=5)
        # Newer events already waiting in the queue.
        client.batch = deque(["c", "d", "e"], maxlen=5)
        # Older, un-sent events come back to the front.
        client._requeue(deque(["a", "b"]))
        self.assertEqual(list(client.batch), ["a", "b", "c", "d", "e"])
        self.assertEqual(client.batch.maxlen, 5)

    def test_requeue_drops_oldest_when_over_cap(self):
        client = _client(_FakeSession(200, 0), max_queue=4)
        client.batch = deque(["c", "d", "e"], maxlen=4)
        # Requeuing 3 older events would make 6 > cap of 4; oldest dropped first.
        client._requeue(deque(["a1", "a2", "a3"]))
        self.assertEqual(len(client.batch), 4)
        # Oldest ("a1", "a2") dropped, front-most retained event is "a3".
        self.assertEqual(list(client.batch), ["a3", "c", "d", "e"])
        self.assertTrue(client._dropping)

    def test_server_error_requeues_within_cap(self):
        async def run():
            # code 8 (server error) + HTTP 503 -> events get requeued.
            session = _FakeSession(503, 8)
            client = _client(session, max_queue=3)
            for i in range(3):
                await client.queue(f"e{i}", send=False)
            with self.assertRaises(Exception):
                await client.send()
            return client

        client = asyncio.run(run())
        # Requeue must not exceed the cap even after a failed send.
        self.assertLessEqual(len(client.batch), client.max_queue)
        self.assertEqual(client.batch.maxlen, 3)

    def test_successful_drain_resets_drop_episode(self):
        async def run():
            session = _FakeSession(200, 0)  # success
            client = _client(session, max_queue=3)
            client._dropping = True  # pretend a prior outage dropped events
            await client.queue("x", send=False)
            await client.send()
            return client

        client = asyncio.run(run())
        self.assertFalse(client._dropping)
        self.assertEqual(len(client.batch), 0)


if __name__ == "__main__":
    unittest.main()

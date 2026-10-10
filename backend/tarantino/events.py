"""In-process pub/sub for live updates, streamed to browsers via SSE."""

import asyncio
import json
from collections.abc import AsyncIterator


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, event_type: str, data: dict) -> None:
        message = {"type": event_type, "data": data}
        for queue in self._subscribers:
            if queue.full():  # slow consumer: drop its oldest event
                queue.get_nowait()
            queue.put_nowait(message)

    async def stream(self, keepalive_seconds: float = 15) -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), keepalive_seconds)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {message['type']}\ndata: {json.dumps(message['data'], default=str)}\n\n"
        finally:
            self._subscribers.discard(queue)

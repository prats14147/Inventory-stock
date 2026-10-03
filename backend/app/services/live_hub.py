"""
backend/app/services/live_hub.py

In-process pub/sub used to push real-time frames (live sales events,
proactive alerts) to every connected WebSocket client.

SCOPE, STATED HONESTLY: this is a single-process hub. It matches this app's
deployment shape (one uvicorn worker + Postgres, see docker-compose.yml), and
it is what makes the live dashboard update without any polling. It is not a
distributed broker: running multiple worker processes would give each worker
its own subscriber set, and a production version of this feature would
publish through Redis pub/sub instead. The interface below is intentionally
tiny so that swap is local to this file.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import AsyncIterator, Optional

log = logging.getLogger("live_hub")


class LiveEventHub:
    """Fans one published frame out to every active subscriber queue.

    Thread-safety: publishers are not always on the event loop. The simulator
    ticks inside a worker thread (`anyio.to_thread.run_sync`) and the REST
    endpoints run in Starlette's threadpool, while the subscriber queues
    belong to the serving loop. `publish()` therefore hops back onto the loop
    with `call_soon_threadsafe` whenever it is called from another thread --
    without this, frames would be enqueued but never wake the awaiting
    coroutine, and the live dashboard would appear frozen.
    """

    def __init__(self, max_buffer: int = 200):
        self._subscribers: set["asyncio.Queue[dict]"] = set()
        self._max_buffer = max_buffer
        self._published = 0
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator["asyncio.Queue[dict]"]:
        """Register a queue for the duration of the `async with` block."""
        queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=self._max_buffer)
        self._loop = asyncio.get_running_loop()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    def publish(self, frame: dict) -> None:
        """Deliver `frame` to all subscribers, never blocking the producer."""
        self._published += 1

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if self._loop is not None and running is not self._loop:
            # Off-loop publisher: hand delivery to the loop that owns the queues.
            try:
                self._loop.call_soon_threadsafe(self._deliver, frame)
            except RuntimeError:  # loop already closed
                pass
            return

        self._deliver(frame)

    def _deliver(self, frame: dict) -> None:
        """Must run on the subscribers' loop."""
        for queue in list(self._subscribers):
            if queue.full():
                # Slow consumer: drop its oldest frame rather than stalling the
                # producer or growing memory without bound. The newest state is
                # what a live dashboard wants, and every frame is persisted in
                # Postgres anyway, so nothing is truly lost.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                log.warning("Live subscriber fell behind; dropped its oldest frame")
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(frame)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def stats(self) -> dict:
        return {
            "subscribers": self.subscriber_count,
            "frames_published": self._published,
            "max_buffer": self._max_buffer,
        }


_hub: Optional[LiveEventHub] = None


def get_live_hub() -> LiveEventHub:
    global _hub
    if _hub is None:
        _hub = LiveEventHub()
    return _hub


def set_live_hub(hub: Optional[LiveEventHub]) -> None:
    """Override the global hub (used by tests)."""
    global _hub
    _hub = hub

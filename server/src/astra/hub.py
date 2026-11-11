"""The WebSocket fan-out.

Each connected client owns a bounded queue that the endpoint coroutine drains.
Publishing only schedules the fan-out on the event loop, so the serial and
replay threads never wait on a browser. A client whose queue fills is closed:
it cannot keep up and must not slow the rest.
"""

import asyncio
import contextlib

from fastapi import WebSocket

from astra.contract import (
    DeviceStatusMessage,
    ErrorMessage,
    InsightMessage,
    ModelRunMessage,
    TelemetryMessage,
)

Message = (
    TelemetryMessage
    | InsightMessage
    | DeviceStatusMessage
    | ErrorMessage
    | ModelRunMessage
)

QUEUE_SIZE = 256


class Hub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: dict[WebSocket, asyncio.Queue[str]] = {}
        self._closing: set[asyncio.Task[None]] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add(self, socket: WebSocket) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._queues[socket] = queue
        return queue

    def remove(self, socket: WebSocket) -> None:
        self._queues.pop(socket, None)

    def publish(self, message: Message) -> None:
        data = message.model_dump_json()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._fanout, data)

    def _fanout(self, data: str) -> None:
        slow = []
        for socket, queue in self._queues.items():
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                slow.append(socket)
        for socket in slow:
            self._queues.pop(socket, None)
            task = asyncio.ensure_future(self._close(socket))
            task.add_done_callback(self._closing.discard)
            self._closing.add(task)

    @staticmethod
    async def _close(socket: WebSocket) -> None:
        with contextlib.suppress(RuntimeError, OSError):
            await socket.close(code=1013)

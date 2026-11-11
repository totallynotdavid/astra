"""The WebSocket fan-out.

Each connected client owns a bounded queue that the endpoint coroutine drains.
Publishing only schedules the fan-out on the event loop, so the serial and
replay threads never wait on a browser. A client whose queue fills is closed:
it cannot keep up and must not slow the rest.

A client bound to a crew member gets each message through `view`, which
returns the part that member may see, or None. Without a `view`, a bound
client gets nothing.
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _Client:
    queue: asyncio.Queue[str]
    member_id: str | None


class Hub:
    def __init__(self, view: Callable[[Message, str], Message | None] | None = None):
        self._view = view
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: dict[WebSocket, _Client] = {}
        self._closing: set[asyncio.Task[None]] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add(
        self, socket: WebSocket, member_id: str | None = None
    ) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._clients[socket] = _Client(queue, member_id)
        return queue

    def remove(self, socket: WebSocket) -> None:
        self._clients.pop(socket, None)

    def publish(self, message: Message) -> None:
        data = message.model_dump_json()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._fanout, message, data)

    def _fanout(self, message: Message, data: str) -> None:
        slow = []
        for socket, client in self._clients.items():
            text = data if client.member_id is None else self._scoped(message, client)
            if text is None:
                continue
            try:
                client.queue.put_nowait(text)
            except asyncio.QueueFull:
                slow.append(socket)
        for socket in slow:
            self._clients.pop(socket, None)
            task = asyncio.ensure_future(self._close(socket))
            task.add_done_callback(self._closing.discard)
            self._closing.add(task)

    def _scoped(self, message: Message, client: _Client) -> str | None:
        if self._view is None or client.member_id is None:
            return None
        visible = self._view(message, client.member_id)
        return visible.model_dump_json() if visible is not None else None

    @staticmethod
    async def _close(socket: WebSocket) -> None:
        with contextlib.suppress(RuntimeError, OSError):
            await socket.close(code=1013)

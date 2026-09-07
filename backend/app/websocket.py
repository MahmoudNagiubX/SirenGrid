from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

__all__ = [
    "router",
    "OperationsConnectionManager",
    "operations_manager",
    "publish_operations_event",
    "reset_operations_stream",
]

router = APIRouter(tags=["operations"])


class OperationsConnectionManager:
    """Process-local connection manager for the operations WebSocket stream.

    Maintains active WebSocket connections and a process-local global monotonically
    increasing stream sequence. The sequence starts from deterministic 0 on backend
    startup and increments exactly once for each published operations event during
    that process lifetime.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._sequence: int = 0
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    @property
    def current_sequence(self) -> int:
        with self._lock:
            return self._sequence

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        with self._lock:
            self.active_connections.append(websocket)
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def disconnect(self, websocket: WebSocket) -> None:
        with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    def publish(
        self,
        *,
        event: str,
        incident_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Publish an operations event with a monotonically increasing process-local stream sequence.

        Increments the sequence exactly once and delivers the envelope to all active
        connections. Returns the constructed envelope dictionary.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._sequence += 1
            seq = self._sequence
            conns = list(self.active_connections)
            loop = self.loop

        envelope: dict[str, Any] = {
            "event": event,
            "incident_id": incident_id,
            "timestamp": now_iso,
            "version": seq,
            "payload": payload,
        }

        if not conns or loop is None:
            return envelope

        dead: list[WebSocket] = []
        for ws in conns:
            coro = ws.send_json(envelope)
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is loop:
                loop.create_task(coro)
            elif loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                try:
                    future.result(timeout=5.0)
                except Exception:
                    dead.append(ws)
            else:
                try:
                    asyncio.run(coro)
                except Exception:
                    dead.append(ws)

        if dead:
            with self._lock:
                for ws in dead:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)

        return envelope

    def reset(self) -> None:
        """Reset sequence and active connections for test isolation."""
        with self._lock:
            self._sequence = 0
            self.active_connections.clear()
            self.loop = None


operations_manager = OperationsConnectionManager()


def publish_operations_event(
    *,
    event: str,
    incident_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Publish an operations event to the process-local stream manager."""
    return operations_manager.publish(
        event=event,
        incident_id=incident_id,
        payload=payload,
    )


def reset_operations_stream() -> None:
    """Reset the operations stream sequence and active connections for testing."""
    operations_manager.reset()


@router.websocket("/ws/operations")
async def websocket_operations(websocket: WebSocket) -> None:
    """Operations realtime WebSocket stream endpoint: /api/v1/ws/operations.

    Delivers live operational invalidation and event notifications.
    Clients receive strictly monotonically sequenced envelopes.
    Clients use REST endpoints for recovery after disconnects or sequence gaps.
    """
    await operations_manager.connect(websocket)
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        operations_manager.disconnect(websocket)

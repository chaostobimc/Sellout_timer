from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

log = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock: self._clients.add(websocket)
        log.info("WebSocket verbunden. Clients: %d", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock: self._clients.discard(websocket)
        log.info("WebSocket getrennt. Clients: %d", len(self._clients))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, ensure_ascii=False)
        async with self._lock: clients = list(self._clients)
        if not clients: return
        results = await asyncio.gather(*[self._safe_send(c, message) for c in clients], return_exceptions=True)
        failed = [c for c, r in zip(clients, results) if r is False or isinstance(r, Exception)]
        if failed:
            async with self._lock:
                for c in failed: self._clients.discard(c)
            log.warning("%d defekte Verbindungen entfernt", len(failed))

    async def _safe_send(self, websocket: WebSocket, message: str) -> bool:
        try:
            await websocket.send_text(message)
            return True
        except (RuntimeError, WebSocketDisconnect, Exception):
            return False

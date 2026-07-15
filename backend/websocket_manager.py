# Source Generated with Decompyle++
# File: websocket_manager.pyc (Python 3.12)

from __future__ import annotations
import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
log = logging.getLogger(__name__)

class WebSocketManager:
    '''Verwaltet alle OBS-Browserquellen und pusht JSON-Events.'''
    
    def __init__(self = None):
        self._clients = set()
        self._lock = asyncio.Lock()

    
    async def connect(self = None, websocket = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def disconnect(self = None, websocket = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def broadcast(self = None, payload = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def _safe_send(self = None, websocket = None, message = None):
        pass
    # WARNING: Decompyle incomplete



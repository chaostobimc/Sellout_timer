# Source Generated with Decompyle++
# File: time_manager.pyc (Python 3.12)

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any
from websocket_manager import WebSocketManager
log = logging.getLogger(__name__)

class TimeManager:
    '''Zentraler Timer im RAM. Keine Maximalzeit-Begrenzung.'''
    
    def __init__(self = None, websocket_manager = None, initial_seconds = None):
        self._ws = websocket_manager
        self._remaining_seconds = max(0, int(initial_seconds))
        self._paused = False
        self._lock = asyncio.Lock()
        self._ticker_task = None
        self._tick_interval = 1

    
    async def start_ticker(self = None, tick_interval = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def stop_ticker(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def _ticker_loop(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def add_time(self = None, seconds = None, source = None, meta = (None,)):
        pass
    # WARNING: Decompyle incomplete

    
    async def remove_time(self = None, seconds = None, source = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def set_time(self = None, seconds = None, source = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def pause(self = None, source = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def resume(self = None, source = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def snapshot(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def get_remaining_seconds(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def broadcast_state(self = None, **extra):
        pass
    # WARNING: Decompyle incomplete



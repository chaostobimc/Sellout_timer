from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.persistence import load_state, save_state
from backend.websocket_manager import WebSocketManager

log = logging.getLogger(__name__)


class TimeManager:
    def __init__(self, websocket_manager: WebSocketManager, initial_seconds: int = 0) -> None:
        self._ws = websocket_manager
        self._remaining_seconds = max(0, int(initial_seconds))
        self._paused = False
        self._multiplier_active = False
        self._multiplier_factor = 1.0
        self._multiplier_until = 0.0
        self._lock = asyncio.Lock()
        self._ticker_task = None
        self._tick_interval = 1.0
        self._restore_state()

    def _restore_state(self) -> None:
        state = load_state()
        saved = state.get("timer_remaining_seconds")
        if saved and saved > 0:
            elapsed = int(time.time() - state.get("timer_saved_at", 0))
            self._remaining_seconds = max(0, int(saved) - elapsed)
            self._paused = bool(state.get("timer_paused", False))
            log.info("Timer wiederhergestellt: %ds", self._remaining_seconds)
        mult_active = state.get("multiplier_active", False)
        mult_until = state.get("multiplier_until", 0)
        if mult_active and mult_until > time.time():
            self._multiplier_active = True
            self._multiplier_factor = float(state.get("multiplier_factor", 2.0))
            self._multiplier_until = float(mult_until)
            log.info("Multiplier wiederhergestellt")

    def _persist(self) -> None:
        try:
            save_state(timer_remaining_seconds=self._remaining_seconds, timer_paused=self._paused, timer_saved_at=time.time(),
                       multiplier_active=self._multiplier_active, multiplier_factor=self._multiplier_factor, multiplier_until=self._multiplier_until)
        except: pass

    async def start_ticker(self, tick_interval: float = 1) -> None:
        self._tick_interval = max(0.2, float(tick_interval))
        if self._ticker_task is not None and not self._ticker_task.done(): return
        self._ticker_task = asyncio.create_task(self._ticker_loop(), name="timer-ticker")
        log.info("Timer-Ticker gestartet")

    async def stop_ticker(self) -> None:
        if self._ticker_task and not self._ticker_task.done():
            self._ticker_task.cancel()
            try: await self._ticker_task
            except asyncio.CancelledError: pass

    async def _ticker_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_interval)
                changed = False
                mult_end = False
                async with self._lock:
                    if self._multiplier_active and time.time() >= self._multiplier_until:
                        self._multiplier_active = False; self._multiplier_factor = 1.0; self._multiplier_until = 0
                        mult_end = True; changed = True
                        log.info("Multiplier abgelaufen")
                    if not self._paused and self._remaining_seconds > 0:
                        self._remaining_seconds = max(0, self._remaining_seconds - int(round(self._tick_interval)))
                        changed = True
                if changed:
                    await self.broadcast_state(reason="multiplier_end" if mult_end else "tick")
                    self._persist()
        except asyncio.CancelledError:
            log.info("Timer-Ticker beendet"); raise
        except Exception: log.exception("Fehler im Timer-Ticker")

    async def add_time(self, seconds: int, source: str = "manual", meta: dict[str, Any] | None = None) -> int:
        seconds = int(seconds)
        if seconds <= 0: return await self.get_remaining_seconds()
        async with self._lock:
            if self._multiplier_active and self._multiplier_factor > 1.0: seconds = int(seconds * self._multiplier_factor)
            self._remaining_seconds += seconds; remaining = self._remaining_seconds
        await self.broadcast_state(reason="add", source=source, seconds_added=seconds, meta=meta or {})
        self._persist(); return remaining

    async def remove_time(self, seconds: int, source: str = "manual") -> int:
        seconds = max(0, int(seconds))
        async with self._lock:
            self._remaining_seconds = max(0, self._remaining_seconds - seconds); remaining = self._remaining_seconds
        await self.broadcast_state(reason="remove", source=source, seconds_removed=seconds)
        self._persist(); return remaining

    async def set_time(self, seconds: int, source: str = "manual") -> int:
        async with self._lock:
            self._remaining_seconds = max(0, int(seconds)); remaining = self._remaining_seconds
        await self.broadcast_state(reason="set", source=source)
        self._persist(); return remaining

    async def pause(self, source: str = "manual") -> None:
        async with self._lock: self._paused = True
        await self.broadcast_state(reason="pause", source=source); self._persist()

    async def resume(self, source: str = "manual") -> None:
        async with self._lock: self._paused = False
        await self.broadcast_state(reason="resume", source=source); self._persist()

    async def set_multiplier_until(self, expires_at: float, factor: float = 2.0, source: str = "hype_train") -> dict:
        async with self._lock:
            now = time.time()
            if expires_at <= now: return {"factor":1.0,"remaining_seconds":0,"active":False}
            self._multiplier_factor = max(1.0, factor); self._multiplier_active = True
            if expires_at > self._multiplier_until: self._multiplier_until = expires_at
            remaining = max(0, int(self._multiplier_until - now))
        await self.broadcast_state(reason="multiplier_set", multiplier_factor=self._multiplier_factor, multiplier_active=True, multiplier_remaining_seconds=remaining, source=source)
        self._persist(); return {"factor":self._multiplier_factor,"remaining_seconds":remaining,"expires_at":expires_at,"active":True}

    async def set_multiplier(self, factor: float = 2.0, duration_minutes: int = 10, source: str = "manual") -> dict:
        async with self._lock:
            self._multiplier_factor = max(1.0, factor); self._multiplier_active = True
            self._multiplier_until = time.time() + max(1, duration_minutes) * 60
            remaining = max(0, int(self._multiplier_until - time.time()))
        await self.broadcast_state(reason="multiplier_set", multiplier_factor=self._multiplier_factor, multiplier_active=True, multiplier_remaining_seconds=remaining, source=source)
        self._persist(); log.info("Multiplier %.1fx für %d Min", factor, duration_minutes); return {"factor":self._multiplier_factor,"duration_minutes":duration_minutes,"remaining_seconds":remaining}

    async def stop_multiplier(self, source: str = "manual") -> None:
        async with self._lock:
            was = self._multiplier_active
            self._multiplier_active = False; self._multiplier_factor = 1.0; self._multiplier_until = 0
        self._persist()
        if was: await self.broadcast_state(reason="multiplier_end", multiplier_active=False, source=source)

    async def get_multiplier_status(self) -> dict:
        async with self._lock:
            if self._multiplier_active:
                r = max(0, int(self._multiplier_until - time.time()))
                return {"multiplier_active":True,"multiplier_factor":self._multiplier_factor,"multiplier_remaining_seconds":r}
            return {"multiplier_active":False,"multiplier_factor":1.0,"multiplier_remaining_seconds":0}

    async def snapshot(self) -> dict:
        async with self._lock:
            mr = max(0, int(self._multiplier_until - time.time())) if self._multiplier_active else 0
            return {"type":"timer_state","remaining_seconds":self._remaining_seconds,"paused":self._paused,"multiplier_active":self._multiplier_active,"multiplier_factor":self._multiplier_factor,"multiplier_remaining_seconds":mr,"server_time":time.time()}

    async def get_remaining_seconds(self) -> int:
        async with self._lock: return self._remaining_seconds

    async def broadcast_state(self, **extra: Any) -> None:
        payload = await self.snapshot(); payload.update(extra)
        await self._ws.broadcast(payload)

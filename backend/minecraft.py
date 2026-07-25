from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Pattern

from backend.events import DonationEvent, EventDispatcher
from backend.persistence import load_state, save_state

log = logging.getLogger(__name__)

def parse_amount(value: str) -> float:
    if value.count(",") == 1: return float(value.replace(".", "").replace(",", "."))
    return float(value.replace(",", ""))


class MinecraftLogScanner:
    def __init__(self, log_path: Path, regex: str | list[str], seconds_per_ingame_dollar: float, dispatcher: EventDispatcher, poll_interval: float = 1, process_existing_lines_on_start: bool = False) -> None:
        self.log_path = Path(log_path)
        self._regex_strings = regex if isinstance(regex, list) else [regex]
        self._patterns = []
        self._compile_patterns()
        self.seconds_per_ingame_dollar = float(seconds_per_ingame_dollar)
        self.dispatcher = dispatcher
        self.poll_interval = max(0.2, float(poll_interval))
        self.process_existing = bool(process_existing_lines_on_start)
        self._task = None; self._stop = asyncio.Event(); self._lock = asyncio.Lock(); self._reset_position = False
        self._restore_state()

    def _restore_state(self) -> None:
        state = load_state()
        sp = state.get("mc_log_path")
        if sp: p = Path(sp); self.log_path = p; log.info("MC Log wiederhergestellt: %s", p)
        sr = state.get("mc_regexes")
        if sr and isinstance(sr, list) and len(sr) > 0: self._regex_strings = list(sr); self._compile_patterns(); log.info("MC Regexes wiederhergestellt")

    def _persist(self) -> None:
        try: save_state(mc_log_path=str(self.log_path), mc_regexes=list(self._regex_strings))
        except: pass

    def _compile_patterns(self) -> None: self._patterns = [re.compile(r) for r in self._regex_strings]

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear(); self._task = asyncio.create_task(self._run(), name="minecraft-scanner")
            log.info("MC Scanner gestartet")

    async def stop(self) -> None:
        if self._task and not self._task.done(): self._stop.set()
        try: await self._task
        except asyncio.CancelledError: pass

    async def set_log_path(self, path: str | Path) -> None:
        async with self._lock: self.log_path = Path(path); self._reset_position = True
        self._persist()

    async def add_regex(self, regex: str) -> None:
        async with self._lock: self._regex_strings.append(regex); self._compile_patterns()
        self._persist()

    async def remove_regex(self, index: int) -> str:
        async with self._lock:
            if 0 <= index < len(self._regex_strings):
                r = self._regex_strings.pop(index); self._compile_patterns(); self._persist(); return r
            return ""

    async def list_regexes(self) -> list[str]:
        async with self._lock: return list(self._regex_strings)

    async def snapshot(self) -> dict:
        async with self._lock: return {"log_path": str(self.log_path), "regex_count": len(self._patterns), "is_running": self._task is not None and not self._task.done()}

    async def _run(self) -> None:
        pos = 0; first = True
        while not self._stop.is_set():
            try:
                async with self._lock:
                    cp = self.log_path
                    if self._reset_position: pos = 0; self._reset_position = False
                if first and not self.process_existing:
                    try: pos = cp.stat().st_size
                    except: pos = 0
                first = False
                try:
                    with open(cp, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(pos); data = f.read(); pos = f.tell()
                    for line in (data.splitlines(keepends=False) if data else []):
                        await self._handle_line(line)
                except FileNotFoundError: await asyncio.sleep(1); continue
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError: break
            except Exception: log.exception("Fehler im MC Scanner"); await asyncio.sleep(2)
        log.info("MC Scanner beendet")

    async def _handle_line(self, line: str) -> None:
        for pattern in self._patterns:
            m = pattern.search(line)
            if m:
                player = m.group("player") if "player" in m.groupdict() else "Unbekannt"
                amt_str = m.group("amount") if "amount" in m.groupdict() else "0"
                try: amt = parse_amount(amt_str)
                except: continue
                seconds = int(amt * self.seconds_per_ingame_dollar)
                if seconds <= 0: continue
                await self.dispatcher.handle_event(DonationEvent(event_type="money", username=player, amount=amt, unit="$", seconds_added=seconds, source="minecraft", message=f"{amt}$"))
                break

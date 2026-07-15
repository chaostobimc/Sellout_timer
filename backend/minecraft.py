# Source Generated with Decompyle++
# File: minecraft.pyc (Python 3.12)

from __future__ import annotations
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Pattern
from events import DonationEvent, EventDispatcher
log = logging.getLogger(__name__)

def parse_amount(value = None):
    if value.count(',') == 1:
        return float(value.replace('.', '').replace(',', '.'))
    return None(float.replace(',', ''))


class MinecraftLogScanner:
    '''Plattformunabhängiger Tail-Scanner für latest.log mit Runtime-Konfiguration.'''
    
    def __init__(self, log_path, regex = None, seconds_per_ingame_dollar = None, dispatcher = None, poll_interval = (1, False), process_existing_lines_on_start = ('log_path', 'Path', 'regex', 'str | list[str]', 'seconds_per_ingame_dollar', 'float', 'dispatcher', 'EventDispatcher', 'poll_interval', 'float', 'process_existing_lines_on_start', 'bool', 'return', 'None')):
        self.log_path = Path(log_path)
        self._regex_strings = regex if isinstance(regex, list) else [
            regex]
        self._patterns = []
        self._compile_patterns()
        self.seconds_per_ingame_dollar = float(seconds_per_ingame_dollar)
        self.dispatcher = dispatcher
        self.poll_interval = max(0.2, float(poll_interval))
        self.process_existing = bool(process_existing_lines_on_start)
        self._task = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._reset_position = False

    
    def _compile_patterns(self = None):
        patterns = []
        for regex in self._regex_strings:
            patterns.append(re.compile(regex))
        self._patterns = patterns

    
    def start(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def stop(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def set_log_path(self = None, path = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def add_regex(self = None, regex = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def remove_regex(self = None, index = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def list_regexes(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def snapshot(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def _run(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    def _read_new_lines(self = None, log_path = None, position = None):
        f = open(log_path, 'r', encoding = 'utf-8', errors = 'ignore')
        f.seek(position)
        data = f.read()
        new_position = f.tell()
        None(None, None)
    # WARNING: Decompyle incomplete

    
    async def _handle_line(self = None, line = None):
        pass
    # WARNING: Decompyle incomplete



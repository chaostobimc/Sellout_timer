# Source Generated with Decompyle++
# File: discord_bot.pyc (Python 3.12)

from __future__ import annotations
import asyncio
import logging
import os
import re
from pathlib import Path
from events import SoundManager
from minecraft import MinecraftLogScanner
from time_manager import TimeManager
log = logging.getLogger(__name__)

def parse_duration_to_seconds(value = None):
    value = value.strip().lower().replace(' ', '')
    if value.isdigit():
        return int(value)
# WARNING: Decompyle incomplete


class DiscordEmergencyBot:
    
    def __init__(self = None, time_manager = None, config = None, sound_manager = (None, None), minecraft_scanner = ('time_manager', 'TimeManager', 'config', 'dict', 'sound_manager', 'SoundManager | None', 'minecraft_scanner', 'MinecraftLogScanner | None', 'return', 'None')):
        self.time_manager = time_manager
        self.sound_manager = sound_manager
        self.minecraft_scanner = minecraft_scanner
        self.config = config
    # WARNING: Decompyle incomplete

    
    def start(self = None):
        if not self.token:
            log.warning('Discord Bot nicht gestartet: Token fehlt.')
            return None
        if not self.guild_id:
            self.guild_id
        log.info('Discord Bot Task wird gestartet: token_present=%s admin_count=%d guild_id=%s', bool(self.token), len(self.admin_ids), 'global')
        self._task = asyncio.create_task(self._run(), name = 'discord-emergency-bot')
        self._task.add_done_callback(self._on_task_done)

    
    def _on_task_done(self = None, task = None):
        if task.cancelled():
            return None
        exc = task.exception()
        if exc:
            log.exception('Discord Bot Task abgestürzt', exc_info = exc)
            return None

    
    async def stop(self = None):
        pass
    # WARNING: Decompyle incomplete

    
    async def _run(self = None):
        pass
    # WARNING: Decompyle incomplete



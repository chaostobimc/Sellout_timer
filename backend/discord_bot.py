from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from backend.events import SoundManager
from backend.minecraft import MinecraftLogScanner
from backend.time_manager import TimeManager

log = logging.getLogger(__name__)


def parse_duration_to_seconds(value: str) -> int:
    if not value or not value.strip():
        raise ValueError("Bitte eine Zeit angeben (z.B. 1h30m, 3600, 1:00:00)")
    value = value.strip().lower().replace(" ", "")
    if value.isdigit():
        return int(value)
    if ":" in value:
        parts = value.split(":")
        if not all(p.isdigit() for p in parts):
            raise ValueError("Ungültiges Zeitformat")
        nums = [int(p) for p in parts]
        if len(nums) == 2: return nums[0] * 60 + nums[1]
        if len(nums) == 3: return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 4: return nums[0] * 86400 + nums[1] * 3600 + nums[2] * 60 + nums[3]
    total = 0
    for amount, unit in re.findall(r"(\d+)(d|h|min|m|s)", value):
        mult = {"d": 86400, "h": 3600, "min": 60, "m": 60, "s": 1}
        total += int(amount) * mult[unit]
    if total:
        return total
    raise ValueError("Nutze Sekunden (3600), MM:SS (60:00), HH:MM:SS (1:00:00) oder d/h/min/s (1d2h30m)")


class DiscordEmergencyBot:
    def __init__(self, time_manager: TimeManager, config: dict, sound_manager: SoundManager | None = None, minecraft_scanner: MinecraftLogScanner | None = None) -> None:
        self.time_manager = time_manager
        self.sound_manager = sound_manager
        self.minecraft_scanner = minecraft_scanner
        self.config = config
        admin_ids = set()
        for x in config.get("admin_user_ids", []):
            s = str(x).strip()
            if s: admin_ids.add(int(x))
        self.admin_ids = admin_ids
        self.guild_id = config.get("guild_id")
        self.token = str(config.get("token") or os.getenv(config.get("token_env", "DISCORD_BOT_TOKEN"), "")).strip()
        self._task: asyncio.Task | None = None
        self._bot = None

    def start(self) -> None:
        if not self.token:
            log.warning("Discord Bot nicht gestartet: Token fehlt.")
            return
        log.info("Discord Bot Task wird gestartet: token_present=%s admin_count=%d guild_id=%s", bool(self.token), len(self.admin_ids), self.guild_id or "global")
        self._task = asyncio.create_task(self._run(), name="discord-emergency-bot")
        self._task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled(): return
        exc = task.exception()
        if exc: log.exception("Discord Bot Task abgestürzt", exc_info=exc)

    async def stop(self) -> None:
        if self._bot is not None: await self._bot.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def _run(self) -> None:
        import ssl as ssl_mod
        import aiohttp
        import certifi as certifi_mod
        import discord
        from discord.ext import commands

        intents = discord.Intents.default()
        intents.guilds = True
        ssl_context = ssl_mod.create_default_context(cafile=certifi_mod.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        bot = commands.Bot(command_prefix="!unused", intents=intents, connector=connector)
        self._bot = bot

        def is_admin(interaction: discord.Interaction) -> bool:
            return interaction.user is not None and int(interaction.user.id) in self.admin_ids

        async def begin(interaction: discord.Interaction) -> bool:
            if not is_admin(interaction):
                if not interaction.response.is_done():
                    await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
                return False
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True, thinking=True)
            return True

        async def send(interaction: discord.Interaction, text: str, **kwargs) -> None:
            text = str(text)
            if len(text) > 1900: text = text[:1900] + "\n... gekürzt"
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True, **kwargs)
            else:
                await interaction.response.send_message(text, ephemeral=True, **kwargs)

        async def safe_command(interaction: discord.Interaction, func) -> None:
            if not await begin(interaction): return
            try: await func()
            except Exception as exc:
                log.exception("Discord Command Fehler")
                await send(interaction, f"❌ Fehler:\n```\n{type(exc).__name__}: {exc}\n```")

        @bot.event
        async def on_connect():
            log.info("Discord Bot (Gateway) verbunden")

        @bot.event
        async def on_ready():
            log.info("Discord Bot bereit: %s (ID: %s)", bot.user, bot.user.id if bot.user else "?")
            try:
                await bot.wait_until_ready()
                # Global sync
                synced = await bot.tree.sync()
                log.info("%d Slash-Commands global synchronisiert", len(synced))
                # Guild sync (sofort sichtbar)
                for guild in bot.guilds:
                    try:
                        await bot.tree.sync(guild=guild)
                    except Exception:
                        pass
                log.info("Commands auf %d Guild(s) synchronisiert", len(bot.guilds))
            except Exception:
                log.exception("Fehler beim Sync")

        # --- Help ---
        @bot.tree.command(name="help", description="Zeigt alle Overlay Commands")
        async def help_command(interaction: discord.Interaction):
            async def work():
                cmds = [
                    ("`/help`", "Diese Hilfe"),
                    ("`/timer_set <zeit>`", "Setzt den Timer (z.B. 1h30m, 3600, 1:00:00)"),
                    ("`/timer_add <zeit>`", "Addiert Zeit"),
                    ("`/timer_remove <zeit>`", "Entfernt Zeit"),
                    ("`/timer_pause`", "Pausiert den Timer"),
                    ("`/timer_resume`", "Setzt den Timer fort"),
                    ("`/timer_reset_24h`", "Setzt Timer auf 24h"),
                    ("`/timer_state`", "Zeigt Timer-Status"),
                    ("`/multi [minutes]`", "2x Multiplier für N Minuten"),
                    ("`/multi_stop`", "Multiplier deaktivieren"),
                    ("`/mc_log_browse [path]`", "Dateibrowser für latest.log"),
                    ("`/mc_log_path <path>`", "Setzt latest.log per Pfad"),
                    ("`/mc_status`", "Minecraft Status"),
                    ("`/mc_regex_list`", "Listet Regexe"),
                    ("`/mc_regex_add <regex>`", "Fügt Regex hinzu"),
                    ("`/mc_regex_remove <index>`", "Entfernt Regex"),
                    ("`/sound_play <url>`", "Spielt Sound/Link ab"),
                    ("`/sound_stop`", "Stoppt Sound"),
                    ("`/sound_skip`", "Überspringt Sound"),
                    ("`/sound_clear`", "Leert Sound-Queue"),
                    ("`/sound_volume <percent>`", "Lautstärke 0-100"),
                    ("`/sound_install_tools`", "Prüft/installiert yt-dlp"),
                    ("`/sound_devices`", "Listet Audio-Devices"),
                    ("`/sound_device <id>`", "Setzt Audio-Device"),
                    ("`/env_show`", "Zeigt .env"),
                    ("`/config_path`", "Zeigt Pfade"),
                    ("`/log_tail [lines]`", "Letzte Log-Zeilen"),
                ]
                text = "**Overlay Discord Commands**\n\n" + "\n".join(f"{c}\n    {d}" for c, d in cmds)
                await send(interaction, text)
            await safe_command(interaction, work)

        # --- Timer ---
        @bot.tree.command(name="timer_set", description="Setzt den Timer – z.B. 3600, 1:00:00, 1h30m")
        async def timer_set(interaction: discord.Interaction, zeit: str):
            async def work():
                seconds = parse_duration_to_seconds(zeit)
                remaining = await self.time_manager.set_time(seconds, source="discord")
                await send(interaction, f"✅ Timer auf **{self._format_seconds(remaining)}** gesetzt.")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_add", description="Addiert Zeit – z.B. 30m, 900, 15:00")
        async def timer_add(interaction: discord.Interaction, zeit: str):
            async def work():
                seconds = parse_duration_to_seconds(zeit)
                remaining = await self.time_manager.add_time(seconds, source="discord")
                await send(interaction, f"✅ +{self._format_seconds(seconds)} hinzugefügt. → **{self._format_seconds(remaining)}**")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_remove", description="Entfernt Zeit – z.B. 30m, 900, 15:00")
        async def timer_remove(interaction: discord.Interaction, zeit: str):
            async def work():
                seconds = parse_duration_to_seconds(zeit)
                remaining = await self.time_manager.remove_time(seconds, source="discord")
                await send(interaction, f"✅ -{self._format_seconds(seconds)} entfernt. → **{self._format_seconds(remaining)}**")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_pause", description="Pausiert den Timer")
        async def timer_pause(interaction: discord.Interaction):
            async def work():
                await self.time_manager.pause(source="discord")
                await send(interaction, "⏸ Timer pausiert.")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_resume", description="Setzt den Timer fort")
        async def timer_resume(interaction: discord.Interaction):
            async def work():
                await self.time_manager.resume(source="discord")
                await send(interaction, "▶ Timer fortgesetzt.")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_reset_24h", description="Setzt Timer auf 24h")
        async def timer_reset_24h(interaction: discord.Interaction):
            async def work():
                remaining = await self.time_manager.set_time(86400, source="discord")
                await send(interaction, f"✅ Timer auf **{self._format_seconds(remaining)}** (24h) zurückgesetzt.")
            await safe_command(interaction, work)

        @bot.tree.command(name="timer_state", description="Zeigt Timerstatus")
        async def timer_state(interaction: discord.Interaction):
            async def work():
                snap = await self.time_manager.snapshot()
                remaining = snap.get("remaining_seconds", 0)
                paused = snap.get("paused", False)
                mult_active = snap.get("multiplier_active", False)
                mult_factor = snap.get("multiplier_factor", 1.0)
                mult_remaining = snap.get("multiplier_remaining_seconds", 0)
                status = "⏸ pausiert" if paused else "▶ läuft"
                text = f"⏱ **Timer Status**\nZeit: **{self._format_seconds(remaining)}**\nStatus: {status}"
                if mult_active: text += f"\n🔥 **{mult_factor:.0f}x Multiplier** aktiv – noch {self._format_seconds(mult_remaining)}"
                await send(interaction, text)
            await safe_command(interaction, work)

        # --- Multiplier ---
        @bot.tree.command(name="multi", description="Aktiviert 2x Multiplier für N Minuten")
        async def multi(interaction: discord.Interaction, minutes: int = 10):
            async def work():
                result = await self.time_manager.set_multiplier(factor=2.0, duration_minutes=max(1, minutes), source="discord")
                await send(interaction, f"🔥 **{result['factor']:.0f}x Multiplier** für **{result['duration_minutes']} Minuten** aktiviert!")
            await safe_command(interaction, work)

        @bot.tree.command(name="multi_stop", description="Deaktiviert den Multiplier vorzeitig")
        async def multi_stop(interaction: discord.Interaction):
            async def work():
                await self.time_manager.stop_multiplier(source="discord")
                await send(interaction, "✅ Multiplier deaktiviert.")
            await safe_command(interaction, work)

        # --- Minecraft ---
        class MinecraftBrowserView(discord.ui.View):
            PAGE_SIZE = 20
            def __init__(self, start_path, scanner):
                super().__init__(timeout=300)
                self.scanner = scanner
                self.page = 0
                self.drives_mode = False
                if start_path and Path(start_path).exists():
                    self.path = Path(start_path).expanduser().resolve()
                    if self.path.is_file(): self.path = self.path.parent
                else: self.path = Path.home().resolve()
                self.rebuild()
            def available_drives(self):
                import string as s
                if os.name == "nt": return [Path(f"{l}:\\") for l in s.ascii_uppercase if Path(f"{l}:\\").exists()]
                return [Path("/")]
            def current_entries(self):
                if self.drives_mode: return self.available_drives()
                try: children = list(self.path.iterdir())
                except: return []
                dirs = sorted([p for p in children if p.is_dir()], key=lambda p: p.name.lower())
                logs = sorted([p for p in children if p.is_file() and p.name.lower().endswith(".log")], key=lambda p: p.name.lower())
                return dirs + logs
            def page_entries(self):
                entries = self.current_entries()
                self.page = max(0, min(self.page, max(0, (len(entries)-1)//self.PAGE_SIZE)))
                return entries[self.page*self.PAGE_SIZE:self.page*self.PAGE_SIZE+self.PAGE_SIZE]
            def message_text(self):
                entries = self.current_entries()
                mp = max(1, (len(entries)-1)//self.PAGE_SIZE+1)
                loc = "💽 Laufwerke" if self.drives_mode else str(self.path)
                return f"**Minecraft latest.log auswählen**\nAktueller Ort:\n```\n{loc}\n```\nEinträge: `{len(entries)}` | Seite `{self.page+1}/{mp}`"
            def rebuild(self):
                self.clear_items()
                items = self.page_entries()
                opts = []
                for p in items:
                    pf = "📁 " if p.is_dir() else "📄 " if p.is_file() else "💽 "
                    opts.append(discord.SelectOption(label=pf+p.name[:99], value=str(p)[:100], description="Logdatei" if p.is_file() else "Ordner"))
                if opts:
                    s = discord.ui.Select(placeholder="Auswählen", options=opts[:25], row=0)
                    async def cb(i):
                        try: sel = Path(s.values[0])
                        except: return
                        if sel.is_dir():
                            self.path = sel.resolve(); self.drives_mode = False; self.page = 0
                            self.rebuild(); await i.response.edit_message(content=self.message_text(), view=self)
                        else:
                            await self.scanner.set_log_path(sel)
                            await i.response.edit_message(content=f"✅ Log gesetzt:\n```\n{sel}\n```", view=None)
                    s.callback = cb; self.add_item(s)
                entries = self.current_entries()
                mp = max(0, (len(entries)-1)//self.PAGE_SIZE)
                if self.page > 0:
                    b = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
                    async def pc(i): self.page-=1; self.rebuild(); await i.response.edit_message(content=self.message_text(), view=self)
                    b.callback = pc; self.add_item(b)
                if self.page < mp:
                    b = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, row=1)
                    async def nc(i): self.page+=1; self.rebuild(); await i.response.edit_message(content=self.message_text(), view=self)
                    b.callback = nc; self.add_item(b)
                b = discord.ui.Button(label="🏠", style=discord.ButtonStyle.secondary, row=2)
                async def hc(i): self.path=Path.home().resolve(); self.drives_mode=False; self.page=0; self.rebuild(); await i.response.edit_message(content=self.message_text(), view=self)
                b.callback = hc; self.add_item(b)
                b = discord.ui.Button(label="🔄", style=discord.ButtonStyle.primary, row=2)
                async def rc(i): self.rebuild(); await i.response.edit_message(content=self.message_text(), view=self)
                b.callback = rc; self.add_item(b)

        @bot.tree.command(name="mc_log_browse", description="latest.log per Dateibrowser auswählen")
        async def mc_log_browse(interaction: discord.Interaction, start_path: str = ""):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                view = MinecraftBrowserView(start_path or None, self.minecraft_scanner)
                await interaction.followup.send(content=view.message_text(), view=view, ephemeral=True)
            await safe_command(interaction, work)

        @bot.tree.command(name="mc_log_path", description="Setzt latest.log per Pfad")
        async def mc_log_path(interaction: discord.Interaction, path: str):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                p = Path(path).expanduser().resolve()
                if not p.exists(): await send(interaction, f"❌ Pfad existiert nicht: {p}"); return
                await self.minecraft_scanner.set_log_path(p)
                await send(interaction, f"✅ Log gesetzt:\n```\n{p}\n```")
            await safe_command(interaction, work)

        @bot.tree.command(name="mc_status", description="Minecraft Status")
        async def mc_status(interaction: discord.Interaction):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                snap = await self.minecraft_scanner.snapshot()
                await send(interaction, f"**Minecraft Scanner**\nLog: `{snap.get('log_path','?')}`\nRegexes: {snap.get('regex_count',0)}\nLäuft: {snap.get('is_running',False)}")
            await safe_command(interaction, work)

        @bot.tree.command(name="mc_regex_list", description="Listet Minecraft Regexe")
        async def mc_regex_list(interaction: discord.Interaction):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                regexes = await self.minecraft_scanner.list_regexes()
                if not regexes: await send(interaction, "Keine Regexe definiert."); return
                await send(interaction, "**Regexe:**\n" + "\n".join(f"`[{i}]` {r}" for i,r in enumerate(regexes)))
            await safe_command(interaction, work)

        @bot.tree.command(name="mc_regex_add", description="Fügt Minecraft Regex hinzu")
        async def mc_regex_add(interaction: discord.Interaction, regex: str):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                await self.minecraft_scanner.add_regex(regex)
                await send(interaction, f"✅ Regex hinzugefügt:\n`{regex}`")
            await safe_command(interaction, work)

        @bot.tree.command(name="mc_regex_remove", description="Entfernt Regex per Index")
        async def mc_regex_remove(interaction: discord.Interaction, index: int):
            async def work():
                if not self.minecraft_scanner: await send(interaction, "Minecraft Scanner nicht aktiviert."); return
                removed = await self.minecraft_scanner.remove_regex(index)
                if removed: await send(interaction, f"✅ Regex entfernt:\n`{removed}`")
                else: await send(interaction, f"❌ Ungültiger Index: {index}")
            await safe_command(interaction, work)

        # --- Sound ---
        @bot.tree.command(name="sound_play", description="Spielt Sound per Link")
        async def sound_play(interaction: discord.Interaction, url: str):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager.play(url, requested_by=interaction.user.name, source="discord")
                await send(interaction, f"🎵 Sound wird abgespielt:\n{url}")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_stop", description="Stoppt Sound")
        async def sound_stop(interaction: discord.Interaction):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager.stop(); await send(interaction, "⏹ Sound gestoppt.")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_skip", description="Überspringt aktuellen Sound")
        async def sound_skip(interaction: discord.Interaction):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager._ws.broadcast({"type":"sound_control","action":"skip"})
                await send(interaction, "⏭ Sound übersprungen.")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_clear", description="Leert Sound-Queue")
        async def sound_clear(interaction: discord.Interaction):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager._ws.broadcast({"type":"sound_control","action":"clear"})
                await send(interaction, "🧹 Queue geleert.")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_volume", description="Setzt Lautstärke 0-100")
        async def sound_volume(interaction: discord.Interaction, percent: int):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager.set_volume(max(0, min(100, percent))/100.0)
                await send(interaction, f"🔊 Lautstärke auf **{percent}%** gesetzt.")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_install_tools", description="Installiert/prüft yt-dlp")
        async def sound_install_tools(interaction: discord.Interaction):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await send(interaction, await self.sound_manager.ensure_external_tools())
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_devices", description="Listet Audio Devices")
        async def sound_devices(interaction: discord.Interaction):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                text = await self.sound_manager.list_audio_devices()
                await send(interaction, f"```\n{text[:1800]}\n```")
            await safe_command(interaction, work)

        @bot.tree.command(name="sound_device", description="Setzt Audio Device")
        async def sound_device(interaction: discord.Interaction, device_id: str):
            async def work():
                if not self.sound_manager: await send(interaction, "SoundManager nicht aktiv."); return
                await self.sound_manager.set_output_device(device_id)
                await send(interaction, "Device gesetzt.")
            await safe_command(interaction, work)

        # --- Utility ---
        def runtime_dir() -> Path: return Path(os.getenv("OVERLAY_RUNTIME_DIR", Path.cwd())).resolve()

        def mask_env(text: str, reveal: bool = False) -> str:
            if reveal: return text
            out = []
            for line in text.splitlines():
                if "=" in line and any(k in line.split("=",1)[0].upper() for k in ("TOKEN","SECRET","PASSWORD","OAUTH")):
                    k,v = line.split("=",1); v = v.strip()
                    line = f"{k}={v[:4]}...{v[-4:]}" if v and len(v)>10 else f"{k}=***"
                out.append(line)
            return "\n".join(out)

        @bot.tree.command(name="env_show", description="Zeigt die aktuell verwendete .env")
        async def env_show(interaction: discord.Interaction, reveal_secrets: bool = False):
            async def work():
                env_path = runtime_dir() / ".env"
                if not env_path.exists(): await send(interaction, f"Keine .env:\n```\n{env_path}\n```"); return
                content = mask_env(env_path.read_text("utf-8", errors="replace"), reveal=reveal_secrets)
                await send(interaction, f"Runtime: `{runtime_dir()}`\n.env:\n```env\n{content[:1700]}\n```")
            await safe_command(interaction, work)

        @bot.tree.command(name="config_path", description="Zeigt Runtime-Ordner und Pfade")
        async def config_path(interaction: discord.Interaction):
            async def work():
                rd = runtime_dir()
                await send(interaction, f"Runtime:\n```\n{rd}\n```\n.env:\n```\n{rd/'.env'}\n```\nLog:\n```\n{rd/'logs'/'overlay.log'}\n```")
            await safe_command(interaction, work)

        @bot.tree.command(name="log_tail", description="Zeigt letzte Log-Zeilen")
        async def log_tail(interaction: discord.Interaction, lines: int = 80):
            async def work():
                log_path = runtime_dir() / "logs" / "overlay.log"
                if not log_path.exists(): await send(interaction, f"Log nicht gefunden:\n```\n{log_path}\n```"); return
                all_lines = log_path.read_text("utf-8", errors="replace").splitlines()
                await send(interaction, f"Log: `{log_path}`\n```\n{''.join(all_lines[-max(1,min(lines,200)):])[-1800:]}\n```")
            await safe_command(interaction, work)

        # --- Start ---
        log.info("Discord Commands registriert. Verbinde jetzt zum Gateway...")
        try: await bot.start(self.token)
        except asyncio.CancelledError: raise
        except Exception: log.exception("Discord Bot beendet sich wegen Fehler")

    def _format_seconds(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        parts = []
        if d > 0: parts.append(f"{d}d")
        if h > 0: parts.append(f"{h}h")
        if m > 0: parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.time_manager import TimeManager
from backend.websocket_manager import WebSocketManager

log = logging.getLogger(__name__)

EventType = Literal["follow", "bits", "sub", "gift_sub", "money"]
YOUTUBE_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s]+|youtu\.be/[^\s]+|youtube\.com/shorts/[^\s]+)", re.I)


def extract_first_youtube_url(text: str | None = None) -> str | None:
    if not text: return None
    m = YOUTUBE_RE.search(text)
    return m.group(0).rstrip(").,;!?") if m else None


@dataclass(frozen=True)
class DonationEvent:
    event_type: EventType
    username: str
    amount: float
    unit: str
    seconds_added: int
    source: str
    message: str = ""
    tier: str | None = None
    sound_url: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {"type":"alert","event_type":self.event_type,"username":self.username,"amount":self.amount,"unit":self.unit,"seconds_added":self.seconds_added,"source":self.source,"message":self.message,"tier":self.tier}


class SoundManager:
    def __init__(self, websocket_manager: WebSocketManager, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._ws = websocket_manager
        self.volume = float(cfg.get("volume", 0.75))
        self.max_duration_seconds = min(60, int(cfg.get("max_duration_seconds", 60)))
        self.min_bits_for_youtube = int(cfg.get("min_bits_for_youtube", 10))
        self.output_device_id = str(cfg.get("output_device_id", ""))
        self.playback_mode = "obs_audio_video"
        self.ytdlp_path = str(cfg.get("ytdlp_path", "") or "")
        self.auto_install_tools = bool(cfg.get("auto_install_tools", True))
        self.tools_dir = Path(str(cfg.get("tools_dir", "tools"))).expanduser()
        if not self.tools_dir.is_absolute():
            self.tools_dir = Path(os.getenv("OVERLAY_RUNTIME_DIR", Path.cwd())) / self.tools_dir

    async def broadcast_settings(self) -> None:
        await self._ws.broadcast({"type":"sound_settings","volume":self.volume,"max_duration_seconds":self.max_duration_seconds,"output_device_id":self.output_device_id,"playback_mode":self.playback_mode,"audio_backend":"obs_browser","youtube_resolve":"yt-dlp"})

    async def set_volume(self, volume: float) -> None:
        self.volume = max(0, min(1, float(volume))); await self.broadcast_settings()

    async def set_output_device(self, device_id: str) -> None:
        self.output_device_id = device_id.strip(); await self.broadcast_settings()

    async def list_audio_devices(self) -> str: return f"Sound über OBS.\nYTDLP_PATH={self.ytdlp_path or 'PATH'}"

    async def ensure_external_tools(self) -> str:
        if self._find_ytdlp(): return f"yt-dlp vorhanden: {self._find_ytdlp()}"
        if not self.auto_install_tools: return "Auto-Install deaktiviert."
        if os.name != "nt": return "Auto-Install nur für Windows."
        try:
            self.tools_dir.mkdir(parents=True, exist_ok=True)
            target = self.tools_dir / "yt-dlp.exe"
            await asyncio.to_thread(self._download_file, "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", target)
            self.ytdlp_path = str(target)
            self._write_env_values({"YTDLP_PATH": self.ytdlp_path})
            return f"yt-dlp installiert: {target}"
        except Exception as exc: return f"Download fehlgeschlagen: {exc!r}"

    async def play(self, url: str, requested_by: str = "system", source: str = "manual") -> None:
        url = url.strip()
        if not url: return
        dm, dk = "", ""
        if self._is_youtube_url(url):
            await self.ensure_external_tools()
            dm, dk = await self._resolve_youtube_direct_url(url)
        await self._ws.broadcast({"type":"sound","sound":{"id":f"{int(time.time()*1000)}-{requested_by}","url":url,"direct_media_url":dm,"direct_media_kind":dk,"requested_by":requested_by,"source":source,"volume":self.volume,"max_duration_seconds":self.max_duration_seconds,"muted":False,"visual_only":False,"audio_backend":"obs_browser"}})

    async def stop(self) -> None: await self._ws.broadcast({"type":"sound_control","action":"stop"})
    def _is_youtube_url(self, url: str) -> bool: low = url.lower(); return "youtube.com" in low or "youtu.be" in low

    def _find_ytdlp(self) -> str:
        if self.ytdlp_path and Path(self.ytdlp_path).expanduser().exists(): return self.ytdlp_path
        return shutil.which("yt-dlp") or shutil.which("yt-dlp.exe") or ""

    async def _resolve_youtube_direct_url(self, url: str) -> tuple[str, str]:
        ytdlp = self._find_ytdlp()
        if not ytdlp: return ("", "")
        cmd = [ytdlp, "--no-playlist", "--no-warnings", "-f", "b[ext=mp4]/best[ext=mp4]/b/best", "-g", url]
        try:
            extra = {}
            if os.name == "nt":
                import subprocess as _sp; extra["creationflags"] = _sp.CREATE_NO_WINDOW
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=self._tool_env(), **extra)
            out, err = await asyncio.wait_for(proc.communicate(), timeout=25)
            lines = [l.strip() for l in out.decode("utf-8", errors="replace").splitlines() if l.strip().startswith("http")]
            if lines: return (lines[0], "video")
            log.warning("yt-dlp keine URL: %s", err.decode("utf-8", errors="replace")[:200])
            return ("", "")
        except Exception:
            log.exception("yt-dlp fehlgeschlagen"); return ("", "")

    def _tool_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.ytdlp_path:
            try: env["PATH"] = str(Path(self.ytdlp_path).expanduser().resolve().parent) + os.pathsep + env.get("PATH", "")
            except: pass
        return env

    def _download_file(self, url: str, target: Path) -> None:
        import urllib.request as urllib
        target.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.Request(url, headers={"User-Agent": "overlay-system/1.0"})
        with urllib.urlopen(req, timeout=120) as r: target.write_bytes(r.read())

    def _write_env_values(self, values: dict[str, str]) -> None:
        env_path = Path(os.getenv("OVERLAY_RUNTIME_DIR", Path.cwd())) / ".env"
        try:
            existing = env_path.read_text("utf-8") if env_path.exists() else ""
            lines = existing.splitlines()
            found = set()
            new_lines = []
            for line in lines:
                if "=" in line and not line.lstrip().startswith("#"):
                    key = line.split("=", 1)[0].strip()
                    if key in values:
                        new_lines.append(f"{key}={str(values[key] or '').replace(chr(92), '/')}")
                        found.add(key); continue
                new_lines.append(line)
            for k, v in values.items():
                if k not in found:
                    new_lines.append(f"{k}={str(v or '').replace(chr(92), '/')}")
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception: log.exception(".env Fehler")


class EventDispatcher:
    def __init__(self, time_manager: TimeManager, websocket_manager: WebSocketManager, sound_manager: SoundManager | None = None) -> None:
        self._time = time_manager; self._ws = websocket_manager; self._sound = sound_manager

    async def handle_event(self, event: DonationEvent) -> None:
        log.info("Event: %s von %s amount=%s%s seconds=%s", event.event_type, event.username, event.amount, event.unit, event.seconds_added)
        await self._time.add_time(event.seconds_added, source=event.source, meta=event.to_payload())
        await self._ws.broadcast(event.to_payload())
        if self._sound and event.sound_url:
            if event.event_type == "bits" and event.amount < self._sound.min_bits_for_youtube: return
            if event.event_type in ("sub", "bits", "gift_sub"):
                await self._sound.play(event.sound_url, requested_by=event.username, source=event.source)

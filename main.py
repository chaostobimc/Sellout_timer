from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import Config, load_config
from backend.discord_bot import DiscordEmergencyBot
from backend.events import DonationEvent, EventDispatcher, SoundManager
from backend.minecraft import MinecraftLogScanner
from backend.time_manager import TimeManager
from backend.twitch import TwitchEventSubClient
from backend.websocket_manager import WebSocketManager


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "OverlaySystem_data"
    return Path(__file__).resolve().parent


def get_bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent


def copy_missing_tree(src: Path, dst: Path) -> None:
    import shutil
    if src.exists() and not dst.exists():
        shutil.copytree(src, dst)


def copy_missing_file(src: Path, dst: Path) -> None:
    import shutil
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def ensure_runtime_files(root: Path, bundle_root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    copy_missing_tree(bundle_root / "frontend", root / "frontend")
    copy_missing_tree(bundle_root / "assets", root / "assets")
    copy_missing_file(bundle_root / "config.json", root / "config.json")
    copy_missing_file(bundle_root / ".env.example", root / ".env.example")
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else root
    copy_missing_file(exe_dir / ".env", root / ".env")
    copy_missing_file(exe_dir / "config.json", root / "config.json")
    if not (root / ".env").exists():
        if (bundle_root / ".env").exists():
            copy_missing_file(bundle_root / ".env", root / ".env")
        else:
            copy_missing_file(bundle_root / ".env.example", root / ".env")


ROOT = get_app_root()
BUNDLE_ROOT = get_bundle_root()
ensure_runtime_files(ROOT, BUNDLE_ROOT)
os.environ["OVERLAY_RUNTIME_DIR"] = str(ROOT)
FRONTEND_DIR = ROOT / "frontend"
ASSETS_DIR = ROOT / "assets"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_file_handler = logging.FileHandler(LOG_DIR / "overlay.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
logging.getLogger().addHandler(_file_handler)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
log = logging.getLogger("overlay")


class _SafeNullStream:
    def write(self, _data) -> int: return 0
    def flush(self) -> None: pass
    def isatty(self) -> bool: return False

def ensure_stdio_for_noconsole() -> None:
    if sys.stdout is None: sys.stdout = _SafeNullStream()
    if sys.stderr is None: sys.stderr = _SafeNullStream()
ensure_stdio_for_noconsole()

def configure_ssl_certificates() -> None:
    try:
        import certifi
        cafile = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", cafile)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
        os.environ.setdefault("CURL_CA_BUNDLE", cafile)
        log.info("SSL CA Bundle: %s", cafile)
    except Exception: log.exception("certifi Fehler")
configure_ssl_certificates()

def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "": return default
    return v.strip().lower() in {"1","y","on","yes","true"}
def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "": return default
    return int(v.strip())
def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "": return default
    return float(v.strip().replace(",","."))
def env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is not None: return v.strip()
    return default
def env_bool_auto(name: str, default: bool | str = "auto") -> bool | str:
    v = os.getenv(name)
    if v is None or v.strip() == "": return default
    v = v.strip().lower()
    if v in {"1","y","on","yes","true"}: return True
    if v in {"0","n","no","off","false","disabled"}: return False
    return "auto"
def env_int_list(name: str, default: list[int] | None = None) -> list[int]:
    v = os.getenv(name)
    if not v: return default if default else []
    r = []
    for p in v.replace(";",",").split(","):
        p = p.strip()
        if p: r.append(int(p))
    return r

config: Config = load_config(ROOT / "config.json")
runtime_multipliers = dict(config.multipliers)

# Sicherheitshalber .env direkt einlesen falls python-dotenv nicht installiert ist
_dotenv_path = ROOT / ".env"
if _dotenv_path.exists():
    for _line in _dotenv_path.read_text("utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

for env_name, key in {"SECONDS_PER_FOLLOW":"seconds_per_follow","SECONDS_PER_BIT":"seconds_per_bit","SECONDS_PER_SUB":"seconds_per_sub","SECONDS_PER_TIER2_SUB":"seconds_per_tier2_sub","SECONDS_PER_TIER3_SUB":"seconds_per_tier3_sub","SECONDS_PER_GIFT_SUB":"seconds_per_gift_sub","SECONDS_PER_INGAME_DOLLAR":"seconds_per_ingame_dollar"}.items():
    if os.getenv(env_name) not in (None, ""):
        runtime_multipliers[key] = env_float(env_name, float(runtime_multipliers.get(key, 0)))
# HARDCODED: 1 Bit = 60 Sekunden
runtime_multipliers["seconds_per_bit"] = 60

sound_cfg = dict(config.raw.get("sound", {}))
sound_cfg["enabled"] = env_bool("SOUND_ENABLED", bool(sound_cfg.get("enabled", True)))
sound_cfg["min_bits_for_youtube"] = env_int("SOUND_MIN_BITS_FOR_YOUTUBE", int(sound_cfg.get("min_bits_for_youtube", 10)))
sound_cfg["max_duration_seconds"] = env_int("SOUND_MAX_DURATION_SECONDS", int(sound_cfg.get("max_duration_seconds", 60)))
sound_cfg["volume"] = env_float("SOUND_VOLUME", float(sound_cfg.get("volume", 0.75)))
sound_cfg["output_device_id"] = env_str("SOUND_OUTPUT_DEVICE_ID", str(sound_cfg.get("output_device_id", "")))
sound_cfg["playback_mode"] = env_str("SOUND_PLAYBACK_MODE", str(sound_cfg.get("playback_mode", "python_audio_obs_video")))
sound_cfg["mpv_path"] = env_str("MPV_PATH", str(sound_cfg.get("mpv_path", "mpv")))
sound_cfg["ytdlp_path"] = env_str("YTDLP_PATH", str(sound_cfg.get("ytdlp_path", "")))
sound_cfg["player"] = env_str("SOUND_PLAYER", str(sound_cfg.get("player", "obs")))
sound_cfg["ffplay_path"] = env_str("FFPLAY_PATH", str(sound_cfg.get("ffplay_path", "ffplay")))
sound_cfg["ffmpeg_path"] = env_str("FFMPEG_PATH", str(sound_cfg.get("ffmpeg_path", "ffmpeg")))
sound_cfg["auto_install_tools"] = env_bool("SOUND_AUTO_INSTALL_TOOLS", bool(sound_cfg.get("auto_install_tools", True)))
sound_cfg["tools_dir"] = env_str("SOUND_TOOLS_DIR", str(sound_cfg.get("tools_dir", "tools")))

twitch_cfg = dict(config.twitch)
twitch_cfg["enabled"] = env_bool("TWITCH_ENABLED", bool(twitch_cfg.get("enabled", False)))
twitch_cfg["client_id_env"] = "TWITCH_CLIENT_ID"
twitch_cfg["user_token_env"] = "TWITCH_USER_TOKEN"
twitch_cfg["broadcaster_user_id"] = env_str("TWITCH_BROADCASTER_ID", str(twitch_cfg.get("broadcaster_user_id", "")))
mod_id = env_str("TWITCH_MODERATOR_ID", str(twitch_cfg.get("moderator_user_id", "")))
twitch_cfg["moderator_user_id"] = mod_id or twitch_cfg["broadcaster_user_id"]

discord_cfg = dict(config.discord)
_config_token = str(discord_cfg.get("token") or "").strip()
_env_token = env_str("DISCORD_BOT_TOKEN", "")
discord_cfg["token"] = _config_token or _env_token
discord_cfg["token_env"] = "DISCORD_BOT_TOKEN"
_enabled_raw = env_bool_auto("DISCORD_ENABLED", discord_cfg.get("enabled", "auto"))
if _enabled_raw == "auto" or str(_enabled_raw).strip().lower() == "auto":
    discord_cfg["enabled"] = bool(discord_cfg.get("token"))
else:
    discord_cfg["enabled"] = bool(_enabled_raw)
guild_id_str = env_str("DISCORD_GUILD_ID", str(discord_cfg.get("guild_id") or ""))
discord_cfg["guild_id"] = int(guild_id_str) if guild_id_str else None
admin_ids_env = env_int_list("DISCORD_ADMIN_USER_IDS", discord_cfg.get("admin_user_ids", []))
discord_cfg["admin_user_ids"] = [int(x) for x in admin_ids_env]
log.info("Discord Config: enabled=%s token_present=%s admin_count=%d guild_id=%s",
         discord_cfg.get("enabled"), bool(discord_cfg.get("token")),
         len(discord_cfg.get("admin_user_ids", [])), discord_cfg.get("guild_id") or "global")

ws_manager: WebSocketManager = WebSocketManager()
time_manager: TimeManager = TimeManager(ws_manager, initial_seconds=env_int("TIMER_INITIAL_SECONDS", int(config.timer.get("initial_seconds", 86400))))
sound_manager: SoundManager | None = SoundManager(ws_manager, sound_cfg) if sound_cfg.get("enabled", True) else None
dispatcher: EventDispatcher = EventDispatcher(time_manager, ws_manager, sound_manager)
services: list[Any] = []
minecraft_scanner: MinecraftLogScanner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await time_manager.start_ticker(float(config.timer.get("tick_interval_seconds", 1)))
    if sound_manager: await sound_manager.broadcast_settings()
    if config.minecraft.get("enabled", True):
        regexes = config.minecraft.get("money_regexes") or [config.minecraft.get("money_regex", r"\[(?P<player>.+?)\s*->\s*(?:Dir|You)\]\s*(?P<amount>[0-9]+(?:[.,][0-9]+)?)\$\s*erhalten")]
        mc = MinecraftLogScanner(log_path=config.resolve_path(config.minecraft.get("latest_log_path", "./latest.log")), regex=regexes, seconds_per_ingame_dollar=float(runtime_multipliers.get("seconds_per_ingame_dollar", 0.015)), dispatcher=dispatcher, poll_interval=float(config.minecraft.get("poll_interval_seconds", 1)), process_existing_lines_on_start=bool(config.minecraft.get("process_existing_lines_on_start", False)))
        mc.start(); services.append(mc); minecraft_scanner = mc
    if twitch_cfg.get("enabled", False):
        tw = TwitchEventSubClient(dispatcher, runtime_multipliers, twitch_cfg, time_manager=time_manager)
        tw.start(); services.append(tw)
    if discord_cfg.get("enabled", False):
        db = DiscordEmergencyBot(time_manager, discord_cfg, sound_manager, minecraft_scanner)
        db.start(); services.append(db)
    host = config.server.get("host", "127.0.0.1")
    port = config.server.get("port", 8000)
    log.info("OBS Timer:  http://%s:%s/timer.html", host, port)
    log.info("OBS Alert:  http://%s:%s/alert.html", host, port)
    log.info("OBS Sound:  http://%s:%s/sound.html", host, port)
    log.info("OBS Multi:  http://%s:%s/multiplier.html", host, port)
    log.info("Testseite:  http://%s:%s/test.html", host, port)
    yield
    for service in reversed(services):
        stop = getattr(service, "stop", None)
        if stop:
            try: await stop()
            except Exception: pass
    await time_manager.stop_ticker()

app = FastAPI(title="Twitch/Minecraft Overlay Backend", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

@app.get("/")
async def index():
    return {"status":"ok","timer":"/timer.html","alert":"/alert.html","sound":"/sound.html","multiplier":"/multiplier.html","test":"/test.html","websocket":"/ws"}

@app.get("/timer.html")
async def timer_html():
    return FileResponse(FRONTEND_DIR / "timer.html")

@app.get("/alert.html")
async def alert_html():
    return FileResponse(FRONTEND_DIR / "alert.html")

@app.get("/sound.html")
async def sound_html():
    return FileResponse(FRONTEND_DIR / "sound.html")

@app.get("/multiplier.html")
async def multiplier_html():
    return FileResponse(FRONTEND_DIR / "multiplier.html")

@app.get("/test.html")
async def test_html():
    return FileResponse(FRONTEND_DIR / "test.html")

@app.get("/api/state")
async def state():
    return await time_manager.snapshot()

@app.api_route("/api/test/{event_type}", methods=["GET", "POST"])
async def test_event(event_type: str, username: str = "TestUser", amount: float = 10, message: str = ""):
    if event_type == "follow":
        seconds = int(runtime_multipliers.get("seconds_per_follow", 300))
        event = DonationEvent(event_type="follow", username=username, amount=1, unit="Follow", seconds_added=seconds, source="test", message=message)
    elif event_type == "bits":
        seconds = int(amount * float(runtime_multipliers.get("seconds_per_bit", 60)))
        event = DonationEvent(event_type="bits", username=username, amount=amount, unit="Bits", seconds_added=seconds, source="test", message=message)
    elif event_type in ("sub", "tier2", "tier3", "gift_sub"):
        if event_type == "tier2": key, tier, typ = "seconds_per_tier2_sub", "2000", "sub"
        elif event_type == "tier3": key, tier, typ = "seconds_per_tier3_sub", "3000", "sub"
        elif event_type == "gift_sub": key, tier, typ = "seconds_per_gift_sub", "1000", event_type
        else: key, tier, typ = "seconds_per_sub", "1000", event_type
        seconds = int(amount * float(runtime_multipliers.get(key, 2400)))
        event = DonationEvent(event_type=typ, username=username, amount=amount, unit="Subs", seconds_added=seconds, source="test", message=message, tier=tier)
    elif event_type in ("money", "spende"):
        seconds = int(amount * float(runtime_multipliers.get("seconds_per_ingame_dollar", 0.015)))
        event = DonationEvent(event_type="money", username=username, amount=amount, unit="$", seconds_added=seconds, source="test", message=message)
    else:
        return JSONResponse({"error": "event_type muss follow, bits, sub, gift_sub, tier2, tier3 oder money sein"}, status_code=400)
    await dispatcher.handle_event(event)
    return {"ok": True, "event": event.to_payload(), "timer": await time_manager.snapshot()}

@app.api_route("/api/sound/play", methods=["GET", "POST"])
async def api_sound_play(url: str, username: str = "API"):
    if not sound_manager: return JSONResponse({"error": "sound disabled"}, status_code=400)
    await sound_manager.play(url, requested_by=username, source="api")
    return {"ok": True}

@app.api_route("/api/sound/skip", methods=["POST"])
async def api_sound_skip():
    await ws_manager.broadcast({"type": "sound_control", "action": "skip"})
    return {"ok": True}

@app.api_route("/api/sound/clear", methods=["POST"])
async def api_sound_clear():
    await ws_manager.broadcast({"type": "sound_control", "action": "clear"})
    return {"ok": True}

@app.api_route("/api/multiplier", methods=["GET"])
async def api_multiplier_status():
    return await time_manager.get_multiplier_status()

@app.api_route("/api/multiplier/activate", methods=["POST"])
async def api_multiplier_activate(minutes: int = 10, factor: float = 2.0):
    result = await time_manager.set_multiplier(factor=factor, duration_minutes=max(1, minutes), source="api")
    return {"ok": True, "multiplier": result}

@app.api_route("/api/multiplier/deactivate", methods=["POST"])
async def api_multiplier_deactivate():
    await time_manager.stop_multiplier(source="api")
    return {"ok": True, "multiplier_active": False}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json(await time_manager.snapshot())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("WebSocket beendet", exc_info=True)
    finally:
        await ws_manager.disconnect(websocket)

def main() -> None:
    server_cfg = config.server
    host = env_str("SERVER_HOST", str(server_cfg.get("host", "127.0.0.1")))
    port = env_int("SERVER_PORT", int(server_cfg.get("port", 8000)))
    log_level = env_str("SERVER_LOG_LEVEL", str(server_cfg.get("log_level", "info")))
    uvicorn.run(app, host=host, port=port, log_level=log_level, reload=False, log_config=None, access_log=False)

if __name__ == "__main__":
    main()

# Source Generated with Decompyle++
# File: main.pyc (Python 3.12)

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

def get_app_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'OverlaySystem_data'
    return None(__file__).resolve().parent


def get_bundle_root():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS).resolve()
    return None(__file__).resolve().parent


def copy_missing_tree(src = None, dst = None):
    import shutil
    if src.exists() or dst.exists():
        return None
    shutil.copytree(src, dst)


def copy_missing_file(src = None, dst = None):
    import shutil
    if src.exists():
        if not dst.exists():
            dst.parent.mkdir(parents = True, exist_ok = True)
            shutil.copy2(src, dst)
            return None
        return None


def ensure_runtime_files(root = None, bundle_root = None):
    root.mkdir(parents = True, exist_ok = True)
    copy_missing_tree(bundle_root / 'frontend', root / 'frontend')
    copy_missing_tree(bundle_root / 'assets', root / 'assets')
    copy_missing_file(bundle_root / 'config.json', root / 'config.json')
    copy_missing_file(bundle_root / '.env.example', root / '.env.example')
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else root
    copy_missing_file(exe_dir / '.env', root / '.env')
    copy_missing_file(exe_dir / 'config.json', root / 'config.json')
    if not (root / '.env').exists():
        if (bundle_root / '.env').exists():
            copy_missing_file(bundle_root / '.env', root / '.env')
            return None
        copy_missing_file(bundle_root / '.env.example', root / '.env')
        return None

ROOT = get_app_root()
BUNDLE_ROOT = get_bundle_root()
ensure_runtime_files(ROOT, BUNDLE_ROOT)
os.environ['OVERLAY_RUNTIME_DIR'] = str(ROOT)
FRONTEND_DIR = ROOT / 'frontend'
ASSETS_DIR = ROOT / 'assets'
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(parents = True, exist_ok = True)
_file_handler = logging.FileHandler(LOG_DIR / 'overlay.log', encoding = 'utf-8')
_file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'))
logging.getLogger().addHandler(_file_handler)
logging.basicConfig(level = logging.INFO, format = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')
log = logging.getLogger('overlay')

class _SafeNullStream:
    
    def write(self, _data):
        return 0

    
    def flush(self):
        pass

    
    def isatty(self):
        return False



def ensure_stdio_for_noconsole():
    pass
# WARNING: Decompyle incomplete

ensure_stdio_for_noconsole()

def configure_ssl_certificates():
    '''Fix fuer PyInstaller/Windows: aiohttp/discord/twitch brauchen ein CA Bundle.

    Ohne das kommt in der EXE oft:
    SSL: CERTIFICATE_VERIFY_FAILED unable to get local issuer certificate
    Dann bleiben Twitch und Discord offline.
    '''
    
    try:
        import certifi
        cafile = certifi.where()
        os.environ.setdefault('SSL_CERT_FILE', cafile)
        os.environ.setdefault('REQUESTS_CA_BUNDLE', cafile)
        os.environ.setdefault('CURL_CA_BUNDLE', cafile)
        log.info('SSL CA Bundle gesetzt: %s', cafile)
        return None
    except Exception:
        log.exception('Konnte certifi CA Bundle nicht setzen')
        return None


configure_ssl_certificates()

def env_bool(name = None, default = None):
    value = os.getenv(name)
# WARNING: Decompyle incomplete


def env_int(name = None, default = None):
    value = os.getenv(name)
# WARNING: Decompyle incomplete


def env_float(name = None, default = None):
    value = os.getenv(name)
# WARNING: Decompyle incomplete


def env_str(name = None, default = None):
    value = os.getenv(name)
# WARNING: Decompyle incomplete


def env_bool_auto(name = None, default = None):
    value = os.getenv(name)
# WARNING: Decompyle incomplete


def env_int_list(name = None, default = None):
    value = os.getenv(name)
    if not value:
        if not default:
            default
        return []
    result = None
    for part in value.replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        result.append(int(part))
    return result

config: 'Config' = load_config(ROOT / 'config.json')
runtime_multipliers = dict(config.multipliers)
for env_name, key in {
    'SECONDS_PER_FOLLOW': 'seconds_per_follow',
    'SECONDS_PER_BIT': 'seconds_per_bit',
    'SECONDS_PER_SUB': 'seconds_per_sub',
    'SECONDS_PER_TIER2_SUB': 'seconds_per_tier2_sub',
    'SECONDS_PER_TIER3_SUB': 'seconds_per_tier3_sub',
    'SECONDS_PER_GIFT_SUB': 'seconds_per_gift_sub',
    'SECONDS_PER_INGAME_DOLLAR': 'seconds_per_ingame_dollar' }.items():
    if not os.getenv(env_name) not in (None, ''):
        continue
    runtime_multipliers[key] = env_float(env_name, float(runtime_multipliers.get(key, 0)))
sound_cfg = dict(config.raw.get('sound', { }))
sound_cfg['enabled'] = env_bool('SOUND_ENABLED', bool(sound_cfg.get('enabled', True)))
sound_cfg['min_bits_for_youtube'] = env_int('SOUND_MIN_BITS_FOR_YOUTUBE', int(sound_cfg.get('min_bits_for_youtube', 10)))
sound_cfg['max_duration_seconds'] = env_int('SOUND_MAX_DURATION_SECONDS', int(sound_cfg.get('max_duration_seconds', 120)))
sound_cfg['volume'] = env_float('SOUND_VOLUME', float(sound_cfg.get('volume', 0.75)))
sound_cfg['output_device_id'] = env_str('SOUND_OUTPUT_DEVICE_ID', str(sound_cfg.get('output_device_id', '')))
sound_cfg['playback_mode'] = env_str('SOUND_PLAYBACK_MODE', str(sound_cfg.get('playback_mode', 'python_audio_obs_video')))
sound_cfg['mpv_path'] = env_str('MPV_PATH', str(sound_cfg.get('mpv_path', 'mpv')))
sound_cfg['ytdlp_path'] = env_str('YTDLP_PATH', str(sound_cfg.get('ytdlp_path', '')))
sound_cfg['player'] = env_str('SOUND_PLAYER', str(sound_cfg.get('player', 'obs')))
sound_cfg['ffplay_path'] = env_str('FFPLAY_PATH', str(sound_cfg.get('ffplay_path', 'ffplay')))
sound_cfg['ffmpeg_path'] = env_str('FFMPEG_PATH', str(sound_cfg.get('ffmpeg_path', 'ffmpeg')))
sound_cfg['auto_install_tools'] = env_bool('SOUND_AUTO_INSTALL_TOOLS', bool(sound_cfg.get('auto_install_tools', True)))
sound_cfg['tools_dir'] = env_str('SOUND_TOOLS_DIR', str(sound_cfg.get('tools_dir', 'tools')))
twitch_cfg = dict(config.twitch)
twitch_cfg['enabled'] = env_bool('TWITCH_ENABLED', bool(twitch_cfg.get('enabled', False)))
twitch_cfg['client_id_env'] = 'TWITCH_CLIENT_ID'
twitch_cfg['user_token_env'] = 'TWITCH_USER_TOKEN'
twitch_cfg['broadcaster_user_id'] = env_str('TWITCH_BROADCASTER_ID', str(twitch_cfg.get('broadcaster_user_id', '')))
if not env_str('TWITCH_MODERATOR_ID', str(twitch_cfg.get('moderator_user_id', ''))):
    env_str('TWITCH_MODERATOR_ID', str(twitch_cfg.get('moderator_user_id', '')))
twitch_cfg['moderator_user_id'] = twitch_cfg['broadcaster_user_id']
discord_cfg = dict(config.discord)
if not discord_cfg.get('token'):
    discord_cfg.get('token')
_config_token = str('').strip()
_env_token = env_str('DISCORD_BOT_TOKEN', '')
if not _config_token:
    _config_token
discord_cfg['token'] = _env_token
discord_cfg['token_env'] = 'DISCORD_BOT_TOKEN'
_enabled_raw = env_bool_auto('DISCORD_ENABLED', discord_cfg.get('enabled', 'auto'))
if _enabled_raw == 'auto' or str(_enabled_raw).strip().lower() == 'auto':
    discord_cfg['enabled'] = bool(discord_cfg.get('token'))
else:
    discord_cfg['enabled'] = bool(_enabled_raw)
if not discord_cfg.get('guild_id'):
    discord_cfg.get('guild_id')
if not env_str('DISCORD_GUILD_ID', str('')):
    env_str('DISCORD_GUILD_ID', str(''))
discord_cfg['guild_id'] = None
# WARNING: Decompyle incomplete

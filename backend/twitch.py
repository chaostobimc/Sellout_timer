from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
from datetime import datetime, timezone
from typing import Any

import aiohttp
import certifi

from backend.events import DonationEvent, EventDispatcher, extract_first_youtube_url

log = logging.getLogger(__name__)

EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
HELIX_EVENTSUB = "https://api.twitch.tv/helix/eventsub/subscriptions"


class TwitchEventSubClient:
    def __init__(self, dispatcher: EventDispatcher, multipliers: dict[str, float], config: dict[str, Any] | None = None, time_manager=None) -> None:
        self.dispatcher = dispatcher; self.multipliers = multipliers; self.time_manager = time_manager
        cfg = config or {}; self.config = cfg
        self.client_id = os.getenv(self.config.get("client_id_env", "TWITCH_CLIENT_ID"), self.config.get("client_id", ""))
        self.user_token = os.getenv(self.config.get("user_token_env", "TWITCH_USER_TOKEN"), self.config.get("user_token", ""))
        raw_bc = self.config.get("broadcaster_user_id", "") or ""
        self.broadcaster_user_id = str(raw_bc or os.getenv("TWITCH_BROADCASTER_ID", ""))
        raw_mod = self.config.get("moderator_user_id", "") or ""
        self.moderator_user_id = str(raw_mod or self.broadcaster_user_id)
        self._task = None; self._stop = asyncio.Event()

    def start(self) -> None:
        if not (self.client_id and self.user_token and self.broadcaster_user_id):
            log.error("Twitch Credentials fehlen."); return
        if self._task is None or self._task.done():
            self._stop.clear(); self._task = asyncio.create_task(self._run_forever(), name="twitch-eventsub")
            log.info("Twitch EventSub gestartet")

    async def stop(self) -> None:
        if self._task and not self._task.done(): self._stop.set(); self._task.cancel()
        try: await self._task
        except asyncio.CancelledError: pass

    async def _run_forever(self) -> None:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector, headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self.user_token}"}) as session:
            while not self._stop.is_set():
                try: await self._connect_once(session)
                except asyncio.CancelledError: break
                except Exception: log.exception("Fehler, Reconnect 5s"); await asyncio.sleep(5)
        log.info("Twitch beendet")

    async def _connect_once(self, session: aiohttp.ClientSession) -> None:
        async with session.ws_connect(EVENTSUB_WS_URL) as ws:
            log.info("Twitch WebSocket verbunden")
            async for msg in ws:
                if self._stop.is_set(): break
                if msg.type == aiohttp.WSMsgType.TEXT: await self._handle_ws_message(session, json.loads(msg.data))
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR): break

    async def _handle_ws_message(self, session: aiohttp.ClientSession, data: dict) -> None:
        meta = data.get("metadata", {}); payload = data.get("payload", {}); mt = meta.get("message_type", "")
        if mt == "session_welcome":
            sid = payload.get("session", {}).get("id")
            if sid: log.info("Session-ID erhalten, abonniere..."); await self._subscribe_all(session, sid)
        elif mt == "session_reconnect":
            ru = payload.get("session", {}).get("reconnect_url")
            if ru: raise aiohttp.WebSocketError(0, f"Reconnect")
        elif mt == "notification":
            await self._handle_notification(meta.get("subscription_type", ""), payload.get("event", {}))

    async def _subscribe_all(self, session: aiohttp.ClientSession, session_id: str) -> None:
        subs = [
            {"type":"channel.follow","version":"2","condition":{"broadcaster_user_id":self.broadcaster_user_id,"moderator_user_id":self.moderator_user_id}},
            {"type":"channel.cheer","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.subscribe","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.subscription.gift","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.subscription.message","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.hype_train.begin","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.hype_train.progress","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
            {"type":"channel.hype_train.end","version":"1","condition":{"broadcaster_user_id":self.broadcaster_user_id}},
        ]
        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}
        for sub in subs:
            body = {"type":sub["type"],"version":sub["version"],"condition":sub["condition"],"transport":{"method":"websocket","session_id":session_id}}
            try:
                async with session.post(HELIX_EVENTSUB, headers=headers, json=body) as resp:
                    if resp.status == 202: log.info("Abonniert: %s", sub["type"])
                    else: log.warning("%s fehlgeschlagen: %s", sub["type"], await resp.text())
            except: log.exception("EventSub Fehler %s", sub["type"])

    def _tier_multiplier_key(self, tier: str) -> str:
        if tier == "2000": return "seconds_per_tier2_sub"
        if tier == "3000": return "seconds_per_tier3_sub"
        return "seconds_per_sub"

    async def _handle_notification(self, sub_type: str, e: dict[str, Any]) -> None:
        if sub_type == "channel.follow":
            await self.dispatcher.handle_event(DonationEvent(event_type="follow", username=e.get("user_name","Unbekannt"), amount=1, unit="Follow", seconds_added=int(float(self.multipliers.get("seconds_per_follow",300))), source="twitch"))
        elif sub_type == "channel.cheer":
            bits = int(e.get("bits",0)); msg = e.get("message","")
            seconds = int(bits * float(self.multipliers.get("seconds_per_bit",60)))
            await self.dispatcher.handle_event(DonationEvent(event_type="bits", username=e.get("user_name","Unbekannt"), amount=bits, unit="Bits", seconds_added=seconds, source="twitch", message=msg, sound_url=extract_first_youtube_url(msg)))
        elif sub_type == "channel.subscribe":
            tier = e.get("tier","1000")
            seconds = int(float(self.multipliers.get(self._tier_multiplier_key(tier),2400)))
            await self.dispatcher.handle_event(DonationEvent(event_type="sub", username=e.get("user_name","Sub"), amount=1, unit="Sub", seconds_added=seconds, source="twitch", tier=tier))
        elif sub_type == "channel.subscription.gift":
            tier = e.get("tier","1000"); total = int(e.get("total",1) or 1)
            seconds = int(total * float(self.multipliers.get(self._tier_multiplier_key(tier),2400)))
            await self.dispatcher.handle_event(DonationEvent(event_type="gift_sub", username=e.get("user_name","Gifter"), amount=total, unit="Subs", seconds_added=seconds, source="twitch", tier=tier))
        elif sub_type == "channel.subscription.message":
            tier = e.get("tier","1000")
            msg = e.get("message",{}).get("text","") if isinstance(e.get("message"),dict) else str(e.get("message",""))
            seconds = int(float(self.multipliers.get(self._tier_multiplier_key(tier),2400)))
            await self.dispatcher.handle_event(DonationEvent(event_type="sub", username=e.get("user_name","Sub"), amount=1, unit="Sub", seconds_added=seconds, source="twitch", tier=tier, message=msg, sound_url=extract_first_youtube_url(msg)))
        elif sub_type in ("channel.hype_train.begin","channel.hype_train.progress"):
            if not self.time_manager: return
            expires_at_str = e.get("expires_at","")
            if not expires_at_str: return
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z","+00:00")).timestamp()
                level = e.get("level",1)
                await self.time_manager.set_multiplier_until(expires_at=expires_at, factor=2.0, source=f"hype_train_level_{level}")
                log.info("Hype Train Level %d – Multiplier bis %s", level, expires_at_str)
            except Exception as ex: log.exception("Hype-Train Fehler: %s", ex)
        elif sub_type == "channel.hype_train.end":
            if self.time_manager:
                log.info("Hype Train Ende – deaktiviere Multiplier")
                await self.time_manager.stop_multiplier(source="hype_train_end")

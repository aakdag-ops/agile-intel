"""
Slack API client for Agile Intel.
Handles channel listing, message fetching, and user resolution.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class SlackClient:
    BASE = "https://slack.com/api"

    def __init__(self, bot_token: str):
        self.token = bot_token
        self.headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }
        self._user_cache: dict[str, str] = {}

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.BASE}/{endpoint}",
                headers=self.headers,
                params=params or {},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API error on {endpoint}: {data.get('error')}")
            return data

    async def verify(self) -> dict:
        data = await self._get("auth.test")
        return {
            "ok": True,
            "team": data.get("team"),
            "team_id": data.get("team_id"),
            "bot_user": data.get("user"),
            "bot_user_id": data.get("user_id"),
        }

    async def list_channels(self, include_private: bool = False) -> list[dict]:
        types = "public_channel,private_channel" if include_private else "public_channel"
        channels = []
        cursor = None
        while True:
            params = {"types": types, "limit": 200, "exclude_archived": True}
            if cursor:
                params["cursor"] = cursor
            data = await self._get("conversations.list", params)
            for ch in data.get("channels", []):
                channels.append({
                    "id": ch["id"],
                    "name": ch["name"],
                    "is_private": ch.get("is_private", False),
                    "is_member": ch.get("is_member", False),
                    "num_members": ch.get("num_members", 0),
                    "topic": ch.get("topic", {}).get("value", ""),
                })
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return channels

    async def fetch_messages(
        self,
        channel_id: str,
        oldest: Optional[float] = None,
        limit: int = 200,
    ) -> list[dict]:
        params = {"channel": channel_id, "limit": limit}
        if oldest:
            params["oldest"] = str(oldest)
        data = await self._get("conversations.history", params)
        messages = []
        for msg in data.get("messages", []):
            if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
                continue
            if not msg.get("text"):
                continue
            username = await self._resolve_user(msg.get("user", ""))
            messages.append({
                "ts": msg["ts"],
                "user_id": msg.get("user", ""),
                "username": username,
                "text": msg["text"],
                "thread_ts": msg.get("thread_ts"),
                "reply_count": msg.get("reply_count", 0),
                "reactions": [r["name"] for r in msg.get("reactions", [])],
                "timestamp": datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc),
            })
        return messages

    async def _resolve_user(self, user_id: str) -> str:
        if not user_id:
            return "unknown"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            data = await self._get("users.info", {"user": user_id})
            profile = data.get("user", {}).get("profile", {})
            name = profile.get("display_name") or profile.get("real_name") or user_id
            self._user_cache[user_id] = name
            return name
        except Exception:
            return user_id

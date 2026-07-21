"""Throttling middleware — per-user + per-chat rate limits via Redis.

Protects against /guess spam, /collection floods, and abuse.
"""
from __future__ import annotations

import time

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.services.redis_client import get_redis


class ThrottlingMiddleware(BaseMiddleware):
    """Per-user cooldown enforced via Redis INCR + EXPIRE."""

    async def __call__(self, handler, event: TelegramObject, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        redis = get_redis()
        command = self._extract_command(event)
        if not command:
            return await handler(event, data)

        # Different cooldowns per command
        cooldown_map = {
            "guess": 3,
            "collection": 5,
            "fav": 2,
            "gift": 5,
            "trade": 5,
            "topusers": 10,
            "ctop": 10,
            "topgroups": 10,
            "changetime": 30,
            "start": 1,
            "help": 3,
        }
        cd = cooldown_map.get(command, 1)

        key = f"throttle:{user.id}:{command}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, cd)
        if count > 1:
            # silently drop — optionally notify
            if isinstance(event, Message):
                await event.answer(
                    f"⏳ Slow down! Try <code>/{command}</code> again in {cd}s.",
                    parse_mode="HTML",
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(f"⏳ Wait {cd}s", show_alert=False)
            return  # drop the update

        return await handler(event, data)

    @staticmethod
    def _extract_command(event) -> str | None:
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            return event.text.split()[0][1:].split("@")[0].lower()
        if isinstance(event, CallbackQuery) and event.data:
            return event.data.split(":")[0]
        return None

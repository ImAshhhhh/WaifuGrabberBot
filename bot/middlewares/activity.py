"""Group activity tracker — increments the message counter and triggers spawns.

This middleware runs on EVERY group message (not just commands). It:
  1. Ensures the group is registered in the DB.
  2. Updates last_seen for the user.
  3. Calls maybe_spawn() which decides whether to spawn a character.
"""
from __future__ import annotations

import time

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message

from bot.db.pool import get_pool
from bot.services.spawn_engine import maybe_spawn


class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data):
        if not isinstance(event, Message):
            return await handler(event, data)

        chat = event.chat
        if not chat or chat.type == "private":
            return await handler(event, data)

        chat_id = chat.id
        title = chat.title or chat.username or "Private"

        # Light-touch upsert + counter increment
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO groups (chat_id, title, username, last_spawn_at, updated_at)
                VALUES ($1, $2, $3, 0, NOW())
                ON CONFLICT (chat_id) DO UPDATE SET
                  title = EXCLUDED.title,
                  username = EXCLUDED.username,
                  updated_at = NOW()
                """,
                chat_id, title, chat.username,
            )

        # Track user
        user = event.from_user
        if user:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO users (user_id, username, full_name, language_code, last_seen_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                      username = EXCLUDED.username,
                      full_name = EXCLUDED.full_name,
                      language_code = COALESCE(EXCLUDED.language_code, users.language_code),
                      last_seen_at = NOW()
                    """,
                    user.id, user.username, user.full_name, user.language_code,
                )

        # Maybe trigger a spawn
        bot: Bot = data.get("bot") or data.get("event_bot")
        if bot:
            try:
                await maybe_spawn(bot, chat_id, title)
            except Exception as e:
                # Don't break the user's message if spawn fails
                import logging
                logging.getLogger(__name__).warning(f"spawn failed in {chat_id}: {e}")

        return await handler(event, data)

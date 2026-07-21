"""/stats — show your personal stats with a LaTeX formula."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.pool import get_pool
from bot.services.rich_renderer import render_stats_with_math, blocks_to_html

router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user = message.from_user
    if not user:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              u.total_claims,
              COALESCE(s.attempts, 0) AS total_attempts
            FROM users u
            LEFT JOIN (
              SELECT user_id, COUNT(*) AS attempts
              FROM harem WHERE chat_id = $1 GROUP BY user_id
            ) s ON s.user_id = u.user_id
            WHERE u.user_id = $2
            """,
            message.chat.id, user.id,
        )

    stats = {
        "total_caught":   row["total_claims"] if row else 0,
        "total_attempts": max(row["total_attempts"] if row else 0, row["total_claims"] if row else 0),
    }

    blocks = render_stats_with_math(stats)
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")

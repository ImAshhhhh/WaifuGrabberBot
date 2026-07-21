"""/changetime — admins change the spawn interval for a group."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.pool import get_pool
from bot.services.rich_renderer import (
    heading, paragraph, text_bold, text_plain, text_code, blocks_to_html,
)

router = Router()


@router.message(Command("changetime"))
async def cmd_changetime(message: Message):
    user = message.from_user
    chat = message.chat
    if not user or chat.type == "private":
        await message.answer("ℹ️ This command is for groups.", parse_mode="HTML")
        return

    # Check admin status
    member = await message.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await message.answer("🚫 Only group admins can use this.", parse_mode="HTML")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        blocks = [
            heading("⚙️ Change Spawn Interval"),
            paragraph(
                text_plain("Usage: "),
                text_code("/changetime <seconds>"),
                text_plain("\n\nExample: "),
                text_code("/changetime 120"),
                text_plain(" — spawns at most once every 2 minutes."),
            ),
        ]
        try:
            await message.bot.send_rich_message(chat_id=chat.id, blocks=blocks)
        except Exception:
            await message.answer(blocks_to_html(blocks), parse_mode="HTML")
        return

    new_interval = int(parts[1].strip())
    if new_interval < 30 or new_interval > 86400:
        await message.answer("❌ Interval must be between 30 and 86400 seconds.",
                             parse_mode="HTML")
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE groups SET spawn_time_floor = $1, updated_at = NOW() WHERE chat_id = $2",
            new_interval, chat.id,
        )

    await message.answer(
        f"✅ Spawn interval updated to <b>{new_interval}s</b> for this group.",
        parse_mode="HTML",
    )

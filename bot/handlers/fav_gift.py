"""/fav — set a character as favorite, /gift — give a character away."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.game import set_favorite, gift_character
from bot.services.rich_renderer import (
    heading, paragraph, text_bold, text_plain, text_italic,
    blocks_to_html,
)

router = Router()


@router.message(Command("fav"))
async def cmd_fav(message: Message):
    user = message.from_user
    if not user:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        blocks = [
            heading("⭐ Set Favorite"),
            paragraph(
                text_plain("Usage: "),
                text_bold("/fav <character_id>"),
                text_plain("\n\nFind your character IDs with "),
                text_italic("/collection"),
                text_plain("."),
            ),
        ]
        try:
            await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
        except Exception:
            await message.answer(blocks_to_html(blocks), parse_mode="HTML")
        return

    char_id = int(parts[1])
    ok = await set_favorite(user.id, message.chat.id, char_id)
    if ok:
        await message.answer("⭐ <b>Favorite updated!</b> This character is now your showcase.",
                             parse_mode="HTML")
    else:
        await message.answer("❌ You don't own that character in this chat.",
                             parse_mode="HTML")


@router.message(Command("gift"), F.chat.type != "private")
async def cmd_gift(message: Message):
    """Usage: /gift @username <character_id>"""
    user = message.from_user
    if not user:
        return
    parts = message.text.split()
    if len(parts) < 3 or not message.reply_to_message:
        await message.answer(
            "🎁 Usage: reply to a user's message with <code>/gift &lt;character_id&gt;</code>",
            parse_mode="HTML",
        )
        return

    try:
        char_id = int(parts[1])
    except ValueError:
        await message.answer("❌ character_id must be a number.", parse_mode="HTML")
        return

    target = message.reply_to_message.from_user
    if target.id == user.id:
        await message.answer("🚫 You can't gift to yourself.", parse_mode="HTML")
        return

    ok = await gift_character(user.id, target.id, message.chat.id, char_id)
    if ok:
        await message.answer(
            f"🎁 <b>{user.full_name}</b> gifted character #{char_id} to <b>{target.full_name}</b>!",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Couldn't gift. You may not own this character, or it's marked as favorite.",
            parse_mode="HTML",
        )

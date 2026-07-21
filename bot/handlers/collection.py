"""/collection — show the user's harem as a Rich Message slideshow."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.services.game import get_user_harem
from bot.services.rich_renderer import (
    heading, paragraph, text_bold, text_plain, text_italic,
    render_collection_slideshow, blocks_to_html,
)

router = Router()


@router.message(Command("collection"))
async def cmd_collection(message: Message):
    user = message.from_user
    if not user:
        return
    chat_id = message.chat.id
    harem = await get_user_harem(user.id, chat_id, limit=10)
    await _send_collection(message, harem, page=1, total=len(harem))


@router.callback_query(F.data.startswith("collection:"))
async def cb_collection(callback: CallbackQuery):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 1
    user = callback.from_user
    chat_id = callback.message.chat.id
    harem = await get_user_harem(user.id, chat_id, limit=10)
    await _send_collection(callback.message, harem, page=page, total=len(harem))
    await callback.answer()


async def _send_collection(message: Message, harem: list[dict], page: int, total: int):
    if not harem:
        blocks = [
            heading("📦 Your Collection"),
            paragraph(text_plain("Your harem is empty. Wait for a spawn in this group and use "),
                      text_bold("/guess <name>"),
                      text_plain(" to claim your first character!"))
        ]
    else:
        items = [{
            "image_url": h["image_url"],
            "name": h["name"],
            "anime": h["anime"],
            "rarity": h["rarity"],
            "rarity_score": h["rarity_score"],
        } for h in harem]
        blocks = [
            heading(f"📦 {message.from_user.full_name}'s Collection"),
            paragraph(
                text_plain(f"Showing {len(harem)} characters (page {page})."),
                text_plain("  •  Use "),
                text_bold("/fav <id>"),
                text_plain(" to mark a favorite."),
            ),
            render_collection_slideshow(items),
        ]
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")

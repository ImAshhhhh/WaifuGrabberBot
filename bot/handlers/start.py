"""/start and /help handlers."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.utils.markdown import HTML

from bot.config import settings
from bot.services.rich_renderer import (
    heading, paragraph, text_bold, text_italic, text_plain, text_code,
    divider, list_block, blocks_to_html, render_character_card,
)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    blocks = [
        heading("🙋‍♀️✨ Welcome to WaifuGrabberBot!"),
        paragraph(
            text_plain("━━━━━━━━━━━━━━━━━━━━━━\n"),
            text_plain("✨ "),
            text_bold("Every message"),
            text_plain(" brings the next character.\n"),
            text_plain("✨ "),
            text_bold("Every guess"),
            text_plain(" expands your collection.\n"),
            text_plain("✨ "),
            text_bold("Every rarity"),
            text_plain(" brings a new challenge.\n"),
        ),
        divider(),
        paragraph(
            text_plain("🥳 Add me to your group and start your journey today!"),
        ),
        heading("❖ Character Commands"),
        list_block([
            [text_plain("/guess — Catch the spawned character. "), text_italic("(Groups only)")],
            [text_plain("/collection — View your character collection.")],
            [text_plain("/fav — Set a character as your favorite.")],
            [text_plain("/gift — Gift a character. "), text_italic("(Groups only)")],
            [text_plain("/trade — Trade characters. "), text_italic("(Groups only)")],
            [text_plain("/topusers — Global Top Collectors.")],
            [text_plain("/ctop — This Group's Top Collectors.")],
            [text_plain("/topgroups — Global Top Groups.")],
            [text_plain("/changetime — Change spawn interval. "), text_italic("(Admins only)")],
        ]),
    ]

    try:
        await message.bot.send_rich_message(
            chat_id=message.chat.id,
            blocks=blocks,
        )
    except Exception:
        # Fallback to HTML if Rich Messages not supported
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    blocks = [
        heading("📖 Help — How to Play"),
        paragraph(
            text_plain("1️⃣  Add this bot to a group chat.\n"),
            text_plain("2️⃣  After every "),
            text_bold(f"{settings.spawn_msg_interval} messages"),
            text_plain(" in the group (or "),
            text_code(f"{settings.spawn_time_floor}s"),
            text_plain(" of activity), a character spawns.\n"),
            text_plain("3️⃣  Use "),
            text_code("/guess <name>"),
            text_plain(" to claim her before the timer runs out.\n"),
            text_plain("4️⃣  Rarer characters are harder to spawn but score higher."),
        ),
        divider(),
        paragraph(text_bold("Rarity tiers:")),
        list_block([
            [text_plain("🌟 Mythic    — score 95-100  (rarest)")],
            [text_plain("💎 Legendary — score 80-94")],
            [text_plain("🔮 Epic      — score 60-79")],
            [text_plain("⭐ Rare      — score 40-59")],
            [text_plain("🟢 Uncommon  — score 20-39")],
            [text_plain("⚪ Common    — score 1-19  (most frequent)")],
        ]),
    ]
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")

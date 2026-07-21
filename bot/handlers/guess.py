"""/guess — claim the currently spawned character in the group.

Uses Ephemeral Messages (Bot API 10.2) for wrong-guess feedback so the group
chat doesn't get spammed with failed attempts.
"""
from __future__ import annotations

import asyncio
import time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.matcher import matches
from bot.services.spawn_engine import get_active_spawn, clear_active_spawn
from bot.services.game import claim_character
from bot.services.redis_client import get_redis
from bot.handlers.common import spawn_card_html, claim_keyboard

router = Router()


@router.message(Command("guess"), F.chat.type != "private")
async def cmd_guess(message: Message):
    if not message.text:
        return

    # Extract the guessed name (everything after /guess)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _ephemeral_reply(message, "❓ Usage: <code>/guess &lt;name&gt;</code>")
        return

    guess = parts[1].strip()
    user = message.from_user
    chat_id = message.chat.id

    spawn = await get_active_spawn(chat_id)
    if not spawn:
        await _ephemeral_reply(message, "📭 No active spawn in this chat. Wait for the next one!")
        return

    now = int(time.time())
    if now > spawn.get("expires_at", 0):
        await clear_active_spawn(chat_id)
        await _ephemeral_reply(message, "⏰ The spawn has expired. Wait for the next one!")
        return

    # Fuzzy match
    matched, score = matches(guess, spawn["name"], spawn.get("aliases", ""))
    if not matched:
        await _ephemeral_reply(
            message,
            f"❌ Not quite! Match score: <b>{score}/100</b>. Try again!"
        )
        return

    # Attempt atomic claim
    result = await claim_character(
        chat_id=chat_id,
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        spawn=spawn,
    )

    if not result.success:
        if result.reason == "already_owned":
            await _ephemeral_reply(
                message,
                f"🎁 You already own <b>{result.name}</b> in this group!"
            )
        elif result.reason == "expired":
            await _ephemeral_reply(message, "⏰ Spawn expired mid-claim. Race lost!")
        elif result.reason == "no_active_spawn":
            await _ephemeral_reply(message, "🤔 No active spawn — maybe someone else just claimed it.")
        return

    # Claimed! Edit the spawn message to reveal the character
    caption = spawn_card_html(
        result.name, result.anime, result.rarity, result.rarity_score,
        "🎉 Claimed by " + (user.mention_html() or user.full_name),
    )
    try:
        await message.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=spawn["message_id"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=claim_keyboard(result.character_id),
        )
    except Exception:
        pass  # caption edit can fail if message was deleted

    # Public congrats
    congrats = (
        f"🎉 <b>{user.full_name}</b> claimed "
        f"<b>{result.name}</b> ({result.anime}) "
        f"— {result.rarity} (score {result.rarity_score}/100)!"
    )
    await message.answer(congrats, parse_mode="HTML")


async def _ephemeral_reply(message: Message, text: str):
    """Send an ephemeral reply visible only to the calling user.

    Falls back to a regular reply if ephemeral messages aren't supported.
    Uses Bot API 10.2 ephemeral message API.
    """
    try:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            parse_mode="HTML",
            receiver_user_id=message.from_user.id,
        )
    except Exception:
        # Fallback: regular reply (no ephemeral support)
        try:
            await message.reply(text, parse_mode="HTML")
        except Exception:
            pass  # silently drop if everything fails

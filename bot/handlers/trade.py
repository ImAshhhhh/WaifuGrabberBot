"""/trade — propose a character trade with another user."""
from __future__ import annotations

import asyncio
import time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings
from bot.services.game import create_trade, accept_trade
from bot.services.redis_client import get_redis

router = Router()


@router.message(Command("trade"), F.chat.type != "private")
async def cmd_trade(message: Message):
    """Usage: reply to user's message with /trade <your_char_id> <their_char_id>"""
    user = message.from_user
    if not user or not message.reply_to_message:
        await message.answer(
            "🔁 Usage: reply to a user's message with "
            "<code>/trade &lt;your_char_id&gt; &lt;their_char_id&gt;</code>",
            parse_mode="HTML",
        )
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Provide both character IDs.", parse_mode="HTML")
        return

    try:
        your_char = int(parts[1])
        their_char = int(parts[2])
    except ValueError:
        await message.answer("❌ Character IDs must be numbers.", parse_mode="HTML")
        return

    target = message.reply_to_message.from_user
    if target.id == user.id:
        await message.answer("🚫 You can't trade with yourself.", parse_mode="HTML")
        return

    trade_id = await create_trade(
        chat_id=message.chat.id,
        from_uid=user.id,
        to_uid=target.id,
        from_char=your_char,
        to_char=their_char,
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Accept",
            callback_data=f"trade_accept:{trade_id}",
            style="success",
        ),
        InlineKeyboardButton(
            text="❌ Decline",
            callback_data=f"trade_decline:{trade_id}",
            style="danger",
        ),
    ]])

    await message.answer(
        f"🔁 <b>{user.full_name}</b> wants to trade character #{your_char} "
        f"for <b>{target.full_name}</b>'s character #{their_char}.\n\n"
        f"<i>{target.full_name}, you have {settings.trade_window}s to respond.</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Auto-expire after window
    asyncio.create_task(_expire_trade(trade_id, settings.trade_window))


@router.callback_query(F.data.startswith("trade_accept:"))
async def cb_trade_accept(callback: CallbackQuery):
    trade_id = int(callback.data.split(":")[1])
    ok = await accept_trade(trade_id)
    if ok:
        await callback.message.edit_text(
            f"✅ Trade complete! Both characters swapped.",
        )
    else:
        await callback.message.edit_text(
            "❌ Trade failed. One of you no longer owns the offered character."
        )
    await callback.answer()


@router.callback_query(F.data.startswith("trade_decline:"))
async def cb_trade_decline(callback: CallbackQuery):
    trade_id = int(callback.data.split(":")[1])
    from bot.db.pool import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE trades SET status='declined', resolved_at=NOW() WHERE id=$1",
            trade_id,
        )
    await callback.message.edit_text("🚫 Trade declined.")
    await callback.answer()


async def _expire_trade(trade_id: int, after: int):
    await asyncio.sleep(after)
    from bot.db.pool import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE trades SET status='expired', resolved_at=NOW() "
            "WHERE id=$1 AND status='pending'",
            trade_id,
        )

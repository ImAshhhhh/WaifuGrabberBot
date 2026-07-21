"""/changetime and /admin — admin commands.

/changetime is for group admins (change spawn interval).
/admin is for the bot owner only (colorful control panel).
"""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.config import settings
from bot.db.pool import get_pool
from bot.services.rich_renderer import (
    heading, paragraph, text_bold, text_plain, text_code, blocks_to_html,
)

router = Router()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Colorful admin panel — owner only."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏱️ Spawn Interval", callback_data="admin:setspawn", style="primary"),
            InlineKeyboardButton(text="📊 Bot Stats",       callback_data="admin:stats",   style="success"),
        ],
        [
            InlineKeyboardButton(text="🌱 Re-seed Collection", callback_data="admin:seed",  style="primary"),
            InlineKeyboardButton(text="🧹 Clear Spawns",      callback_data="admin:clear", style="danger"),
        ],
        [
            InlineKeyboardButton(text="📣 Broadcast", callback_data="admin:broadcast", style="primary"),
        ],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Owner-only colorful admin panel."""
    user = message.from_user
    if not user or user.id != settings.owner_id:
        await message.answer(
            "🚫 <b>Access denied.</b> Only the bot owner can use this command.",
            parse_mode="HTML",
        )
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        chars = await conn.fetchval("SELECT COUNT(*) FROM characters")
        groups_db = await conn.fetchval("SELECT COUNT(*) FROM groups")

    html = (
        "<b>🎛️ Admin Control Panel</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Your ID:</b> <code>{settings.owner_id}</code>\n"
        f"⏱️ <b>Spawn interval:</b> {settings.spawn_msg_interval} msgs / {settings.spawn_time_floor}s\n"
        f"👥 <b>Total users:</b> {users}\n"
        f"📚 <b>Character pool:</b> {chars}\n"
        f"🌐 <b>Groups:</b> {groups_db}\n\n"
        "<b>👇 Tap an action below.</b>"
    )
    await message.answer(html, parse_mode="HTML", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin(callback):
    if callback.from_user.id != settings.owner_id:
        await callback.answer("🚫 Access denied", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    if action == "stats":
        pool = get_pool()
        async with pool.acquire() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
            chars = await conn.fetchval("SELECT COUNT(*) FROM characters")
            groups_db = await conn.fetchval("SELECT COUNT(*) FROM groups")
            harem = await conn.fetchval("SELECT COUNT(*) FROM harem")
        html = (
            "<b>📊 Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Total users: <b>{users}</b>\n"
            f"📚 Character pool: <b>{chars}</b>\n"
            f"🌐 Registered groups: <b>{groups_db}</b>\n"
            f"💾 Total claims: <b>{harem}</b>\n"
        )
        await callback.message.answer(html, parse_mode="HTML")
    elif action == "setspawn":
        await callback.message.answer(
            "⏱️ Use <code>/changetime &lt;minutes&gt;</code> in a group to set the spawn interval.",
            parse_mode="HTML",
        )
    elif action == "seed":
        await callback.message.answer(
            "🌱 Re-seeding is done at startup. To re-seed manually, run "
            "<code>python -m bot.db.init_db</code> on the server.",
            parse_mode="HTML",
        )
    elif action == "clear":
        await callback.message.answer("🧹 Use the cleanup loop — it auto-expires spawns every 30s.")
    elif action == "broadcast":
        await callback.message.answer(
            "📣 Use <code>/broadcast &lt;message&gt;</code> to send to all groups (not yet implemented in production).",
            parse_mode="HTML",
        )
    await callback.answer()


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

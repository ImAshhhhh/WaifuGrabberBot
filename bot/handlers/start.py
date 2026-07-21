"""/start — redesigned welcome screen with colored buttons.

Layout (per spec):
  Row 1: [➕ Add to Group]                    ← RED (style="danger"), full opacity
  Row 2: [💬 Support] [👑 Owner]              ← one line, green + red combo
  Row 3: [📖 Help Command]                    ← RED
  Row 4: [/guess]      [/collection]          ← green + red combo
  Row 5: [/stats]      [/topusers]            ← red + green combo
  Row 6: [/ctop]       [/admin]               ← green + red combo
  Row 7: [/changetime] [/help]                ← red + green combo

When any command button is clicked → message is EDITED to show:
  - Command name (bold)
  - Description
  - Usage example
  - "⬅️ Back" button to return to main menu
"""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from bot.config import settings

router = Router()

# ─── Command catalog (used by click-to-update) ─────────────────────────────
COMMANDS = {
    "guess": {
        "name": "/guess",
        "title": "🎯 Catch a Character",
        "desc": "Claim the currently-spawned character in a group chat. "
                "First user to type the correct name wins her — she gets added "
                "to your harem with her rarity score.",
        "usage": "/guess <name>\n/example /guess hinata\n/example /guess miku hatsune",
        "where": "Groups only",
    },
    "collection": {
        "name": "/collection",
        "title": "📦 View Your Collection",
        "desc": "Shows every character you've claimed, sorted by rarity. "
                "Your favorite character appears at the top with a ⭐.",
        "usage": "/collection\n/example /collection 2   (page 2)",
        "where": "DM + Groups",
    },
    "stats": {
        "name": "/stats",
        "title": "📊 Your Statistics",
        "desc": "Personal catch stats with a LaTeX-rendered catch-rate formula. "
                "Shows total claims, unique characters, and current spawn interval.",
        "usage": "/stats",
        "where": "DM + Groups",
    },
    "topusers": {
        "name": "/topusers",
        "title": "🏆 Global Top Collectors",
        "desc": "Leaderboard of the top 10 collectors across every group the bot "
                "is in. Ranked by total claims. Renders as a Rich Message table.",
        "usage": "/topusers",
        "where": "DM + Groups",
    },
    "ctop": {
        "name": "/ctop",
        "title": "🏅 Group Top Collectors",
        "desc": "Same as /topusers but scoped to the current group. "
                "See who's dominating your local chat.",
        "usage": "/ctop",
        "where": "Groups only",
    },
    "admin": {
        "name": "/admin",
        "title": "🎛️ Owner Control Panel",
        "desc": "Colorful admin panel restricted to the bot owner. "
                "Buttons: set spawn interval, view bot stats, re-seed your "
                "collection, clear active spawns, broadcast to all groups.",
        "usage": "/admin",
        "where": "DM (owner only)",
    },
    "changetime": {
        "name": "/changetime",
        "title": "⏱️ Change Spawn Interval",
        "desc": "Group admins only. Changes how often a new character spawns "
                "in this group. Default is 10 minutes; range 1-1440 minutes.",
        "usage": "/changetime <minutes>\n/example /changetime 5",
        "where": "Groups (admins)",
    },
    "help": {
        "name": "/help",
        "title": "📖 Full Help",
        "desc": "Complete how-to-play guide with rarity tiers, spawn rules, "
                "and command list.",
        "usage": "/help",
        "where": "DM + Groups",
    },
}


# ─── Keyboard builders ─────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """The /start keyboard — exactly per spec."""
    add_to_group_url = f"https://t.me/{settings.bot_username}?startgroup=true"
    return InlineKeyboardMarkup(inline_keyboard=[
        # Row 1: Add to Group — RED, full opacity
        [InlineKeyboardButton(
            text="➕  Add to Group",
            url=add_to_group_url,
            style="danger",
        )],
        # Row 2: Support + Owner (one line, green + red combo)
        [
            InlineKeyboardButton(text="💬 Support", callback_data="menu:support", style="success"),
            InlineKeyboardButton(text="👑 Owner",   callback_data="menu:owner",   style="danger"),
        ],
        # Row 3: Help Command — RED
        [InlineKeyboardButton(text="📖 Help Command", callback_data="cmd:help", style="danger")],
        # Row 4-7: command buttons, red/green alternating combos
        [
            InlineKeyboardButton(text="/guess",      callback_data="cmd:guess",      style="success"),
            InlineKeyboardButton(text="/collection", callback_data="cmd:collection", style="danger"),
        ],
        [
            InlineKeyboardButton(text="/stats",      callback_data="cmd:stats",      style="danger"),
            InlineKeyboardButton(text="/topusers",   callback_data="cmd:topusers",   style="success"),
        ],
        [
            InlineKeyboardButton(text="/ctop",       callback_data="cmd:ctop",       style="success"),
            InlineKeyboardButton(text="/admin",      callback_data="cmd:admin",      style="danger"),
        ],
        [
            InlineKeyboardButton(text="/changetime", callback_data="cmd:changetime", style="danger"),
            InlineKeyboardButton(text="/help",       callback_data="cmd:help",       style="success"),
        ],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    """Back button shown on detail views."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:back", style="primary"),
    ]])


# ─── Text builders ─────────────────────────────────────────────────────────

WELCOME_HTML = (
    "<b>🙋‍♀️✨ Welcome to WaifuGrabberBot!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✨ Every <b>10 minutes</b>, a new character appears.\n"
    "✨ Every <b>guess</b> expands your collection.\n"
    "✨ Every <b>rarity</b> brings a new challenge.\n\n"
    "<i>🥳 Add me to your group and start your journey today!</i>\n\n"
    "<b>👇 Tap a button below to begin.</b>"
)

SUPPORT_HTML = (
    "<b>💬 Support</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Need help with the bot? Found a bug? Have a feature request?\n\n"
    "• Open an issue: <a href=\"https://github.com/ImAshhhhh/WaifuGrabberBot/issues\">GitHub Issues</a>\n"
    "• Read the docs: <a href=\"https://github.com/ImAshhhhh/WaifuGrabberBot#readme\">README</a>\n"
    "• Deploy your own: <a href=\"https://github.com/ImAshhhhh/WaifuGrabberBot/blob/main/deploy.md\">deploy.md</a>\n\n"
    "<i>This bot is open-source under the MIT license.</i>"
)

OWNER_HTML = (
    "<b>👑 Owner</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>Bot Owner:</b> <code>{owner_id}</code>\n"
    "<b>Repo:</b> <a href=\"https://github.com/ImAshhhhh/WaifuGrabberBot\">ImAshhhhh/WaifuGrabberBot</a>\n"
    "<b>License:</b> MIT\n\n"
    "<i>Built with aiogram 3.30 on Telegram Bot API 10.2.</i>\n"
    "<i>Uses colored buttons (Bot API 9.4), Rich Messages (10.1), Ephemeral Messages (10.2).</i>"
)


def command_detail_html(cmd_key: str) -> str:
    """Build the HTML for a single command's detail view."""
    c = COMMANDS.get(cmd_key)
    if not c:
        return "<b>Unknown command.</b>"
    return (
        f"<b>{c['title']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Command:</b> <code>{c['name']}</code>\n"
        f"<b>Where:</b> <i>{c['where']}</i>\n\n"
        f"<b>Description:</b>\n{c['desc']}\n\n"
        f"<b>Usage:</b>\n<code>{c['usage']}</code>"
    )


# ─── Handlers ──────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Send the welcome message + colored button menu."""
    await message.answer(
        WELCOME_HTML,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Fallback /help — sends the same menu but with a help-focused caption."""
    help_html = (
        "<b>📖 Help — WaifuGrabberBot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>How to play:</b>\n"
        "1️⃣  Add the bot to a group as admin.\n"
        "2️⃣  Every <b>10 minutes</b>, a character spawns.\n"
        "3️⃣  Use <code>/guess &lt;name&gt;</code> to claim her.\n"
        "4️⃣  Rarer characters score higher.\n\n"
        "<b>👇 Tap any command below to see its details.</b>"
    )
    await message.answer(help_html, parse_mode="HTML", reply_markup=main_menu_keyboard())


# ─── Callback handlers (click-to-update-message) ───────────────────────────

@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery):
    """Back button — restore the main menu."""
    try:
        await callback.message.edit_text(
            WELCOME_HTML,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        # If edit fails (e.g. message too old), send a fresh one
        await callback.message.answer(
            WELCOME_HTML,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
            disable_web_page_preview=True,
        )
    await callback.answer("Back to menu")


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            SUPPORT_HTML,
            parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await callback.answer("Support info")


@router.callback_query(F.data == "menu:owner")
async def cb_owner(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            OWNER_HTML.format(owner_id=settings.owner_id or "not set"),
            parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await callback.answer("Owner info")


@router.callback_query(F.data.startswith("cmd:"))
async def cb_command_detail(callback: CallbackQuery):
    """When a command button is clicked, edit the message to show its details."""
    cmd_key = callback.data.split(":", 1)[1]
    if cmd_key not in COMMANDS:
        await callback.answer("Unknown command", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            command_detail_html(cmd_key),
            parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )
    except Exception as e:
        # Fallback: send a new message if edit fails
        await callback.message.answer(
            command_detail_html(cmd_key),
            parse_mode="HTML",
            reply_markup=back_keyboard(),
            disable_web_page_preview=True,
        )
    await callback.answer(f"Showing: /{cmd_key}")

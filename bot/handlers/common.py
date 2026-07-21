"""Common helpers for handlers."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.rich_renderer import rarity_emoji


def spawn_card_html(name: str, anime: str, rarity: str, score: int, desc: str) -> str:
    """HTML caption for the spawn message when a character is claimed."""
    return (
        f"{rarity_emoji(rarity)} <b>{name}</b>\n"
        f"<i>{anime}</i>  •  <b>{rarity}</b> (score {score}/100)\n\n"
        f"<blockquote>{desc}</blockquote>"
    )


def claim_keyboard(character_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⭐ Favorite", callback_data=f"fav:{character_id}", style="primary"),
        InlineKeyboardButton(text="📦 Collection", callback_data="collection:1", style="success"),
    ]])


def admin_check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm", callback_data="admin_confirm", style="success"),
        InlineKeyboardButton(text="❌ Cancel",   callback_data="admin_cancel",   style="danger"),
    ]])

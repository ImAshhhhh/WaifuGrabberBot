"""/topusers /ctop /topgroups — leaderboards rendered as Rich Message tables."""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.game import (
    get_leaderboard_global, get_leaderboard_chat, get_leaderboard_groups,
)
from bot.services.rich_renderer import (
    render_leaderboard_table, blocks_to_html,
)

router = Router()


@router.message(Command("topusers"))
async def cmd_topusers(message: Message):
    top = await get_leaderboard_global(limit=10)
    if not top:
        await message.answer("📭 No collectors yet. Be the first!", parse_mode="HTML")
        return
    rows = [
        [f"{i+1}", u["full_name"][:20], str(u["total_claims"]), u["highest_rarity"] or "—"]
        for i, u in enumerate(top)
    ]
    blocks = render_leaderboard_table(
        title="🏆 Global Top Collectors",
        headers=["#", "User", "Claims", "Best Rarity"],
        rows=rows,
    )
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")


@router.message(Command("ctop"))
async def cmd_ctop(message: Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ /ctop only works in groups.", parse_mode="HTML")
        return
    top = await get_leaderboard_chat(message.chat.id, limit=10)
    if not top:
        await message.answer("📭 No collectors in this group yet.", parse_mode="HTML")
        return
    rows = [
        [f"{i+1}", u["full_name"][:20], str(u["claims"]), str(u["rarity_score"])]
        for i, u in enumerate(top)
    ]
    blocks = render_leaderboard_table(
        title="🏅 This Group's Top Collectors",
        headers=["#", "User", "Claims", "Score"],
        rows=rows,
    )
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")


@router.message(Command("topgroups"))
async def cmd_topgroups(message: Message):
    top = await get_leaderboard_groups(limit=10)
    if not top:
        await message.answer("📭 No groups registered yet.", parse_mode="HTML")
        return
    rows = [
        [f"{i+1}", (g["title"] or g["username"] or "—")[:25],
         str(g["claims"]), str(g["spawns"])]
        for i, g in enumerate(top)
    ]
    blocks = render_leaderboard_table(
        title="🌐 Global Top Groups",
        headers=["#", "Group", "Claims", "Spawns"],
        rows=rows,
    )
    try:
        await message.bot.send_rich_message(chat_id=message.chat.id, blocks=blocks)
    except Exception:
        await message.answer(blocks_to_html(blocks), parse_mode="HTML")

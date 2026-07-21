"""Spawn engine — picks a weighted-random character and posts it to a chat.

Spawns are triggered by EITHER:
  1. message-count threshold (every N group messages), OR
  2. time-floor fallback (if group is active and no spawn in M seconds).

The active spawn is stored in `active_spawns` and in Redis (for fast cooldown
lookups). The Telegram message_id is captured so we can edit it on claim.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import HTML

from bot.config import settings
from bot.db.pool import get_pool
from bot.services.redis_client import get_redis

# Rarity weights — rarer = less frequent
RARITY_WEIGHTS = {
    "Mythic":    1,
    "Legendary": 4,
    "Epic":     12,
    "Rare":     25,
    "Uncommon": 40,
    "Common":   50,
}

# Cache of (id, name, anime, rarity, rarity_score, image_url, aliases) tuples
# Loaded once at startup from Postgres, refreshed periodically.
_character_cache: list[tuple] | None = None
_cache_lock = asyncio.Lock()


@dataclass
class SpawnContext:
    chat_id: int
    character_id: int
    name: str
    anime: str
    rarity: str
    rarity_score: int
    image_url: str
    aliases: str
    message_id: int
    spawned_at: int
    expires_at: int


async def load_character_cache() -> int:
    """Pre-load all characters into memory for fast weighted random."""
    global _character_cache
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, anime, rarity, rarity_score, image_url, aliases "
            "FROM characters"
        )
    _character_cache = [tuple(r) for r in rows]
    return len(_character_cache)


def _pick_weighted() -> tuple:
    """Weighted-random selection from the in-memory cache."""
    if not _character_cache:
        raise RuntimeError("Character cache not loaded")
    weights = [RARITY_WEIGHTS.get(r[3], 10) for r in _character_cache]
    return random.choices(_character_cache, weights=weights, k=1)[0]


def _spawn_caption() -> str:
    """Build the spawn caption — mysterious, no name revealed."""
    return (
        "<b>✨ A new character has appeared!</b>\n\n"
        "🔍 Use <code>/guess &lt;name&gt;</code> to claim her.\n"
        "⏱️ You have <b>90 seconds</b> before she escapes."
    )


def _spawn_keyboard(claim_window: int) -> InlineKeyboardMarkup:
    """Colored inline buttons — uses new Bot API 9.4 `style` field."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎁 Claim Hint",
                callback_data="spawn_hint",
                style="primary",
            ),
            InlineKeyboardButton(
                text="❌ Skip",
                callback_data="spawn_skip",
                style="danger",
            ),
        ],
    ])


async def maybe_spawn(bot: Bot, chat_id: int, title: str) -> SpawnContext | None:
    """Check if a spawn should fire in this chat, and if so, execute it.

    Called from the message-listening middleware after every group message.
    Returns the SpawnContext if a spawn happened, None otherwise.
    """
    pool = get_pool()
    redis = get_redis()
    now = int(time.time())

    # Atomic counter increment in Redis (super fast)
    counter_key = f"grp:{chat_id}:counter"
    last_spawn_key = f"grp:{chat_id}:lastspawn"

    counter = await redis.incr(counter_key)
    await redis.expire(counter_key, 3600)

    last_spawn = int(await redis.get(last_spawn_key) or 0)
    msg_threshold = settings.spawn_msg_interval
    time_floor = settings.spawn_time_floor

    should_spawn = (counter >= msg_threshold) or (
        last_spawn and (now - last_spawn) >= time_floor and counter >= 5
    )

    if not should_spawn:
        return None

    # Reset counter, set last spawn time
    await redis.set(counter_key, 0)
    await redis.set(last_spawn_key, now)

    # Pick a character
    char = _pick_weighted()
    char_id, name, anime, rarity, rarity_score, image_url, aliases = char

    claim_window = settings.spawn_claim_window
    expires_at = now + claim_window

    # Send image with colored buttons
    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=_spawn_caption(),
            parse_mode="HTML",
            reply_markup=_spawn_keyboard(claim_window),
        )
    except Exception as e:
        # Fallback: send as text if image host fails
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"<b>✨ A new character has appeared!</b>\n\n{image_url}\n\n"
                 f"🔍 <code>/guess &lt;name&gt;</code> — 90 seconds to claim!",
            parse_mode="HTML",
            reply_markup=_spawn_keyboard(claim_window),
        )

    # Persist active spawn in DB + Redis
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO active_spawns (chat_id, character_id, message_id, spawned_at, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (chat_id) DO UPDATE SET
              character_id = EXCLUDED.character_id,
              message_id   = EXCLUDED.message_id,
              spawned_at   = EXCLUDED.spawned_at,
              expires_at   = EXCLUDED.expires_at
            """,
            chat_id, char_id, msg.message_id, now, expires_at,
        )
        await conn.execute(
            "INSERT INTO group_stats (chat_id, total_spawns, total_claims) "
            "VALUES ($1, 1, 0) "
            "ON CONFLICT (chat_id) DO UPDATE SET total_spawns = group_stats.total_spawns + 1",
            chat_id,
        )

    spawn_data = {
        "character_id": char_id,
        "name": name,
        "anime": anime,
        "rarity": rarity,
        "rarity_score": rarity_score,
        "image_url": image_url,
        "aliases": aliases,
        "message_id": msg.message_id,
        "spawned_at": now,
        "expires_at": expires_at,
    }
    await redis.set(f"spawn:{chat_id}", json.dumps(spawn_data), ex=claim_window + 10)

    return SpawnContext(
        chat_id=chat_id, character_id=char_id, name=name, anime=anime,
        rarity=rarity, rarity_score=rarity_score, image_url=image_url,
        aliases=aliases, message_id=msg.message_id, spawned_at=now, expires_at=expires_at,
    )


async def get_active_spawn(chat_id: int) -> dict | None:
    """Fetch the currently active spawn in a chat (Redis first, DB fallback)."""
    redis = get_redis()
    raw = await redis.get(f"spawn:{chat_id}")
    if raw:
        return json.loads(raw)
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT s.*, c.name, c.anime, c.rarity, c.rarity_score, c.image_url, c.aliases "
            "FROM active_spawns s JOIN characters c ON c.id = s.character_id "
            "WHERE s.chat_id = $1",
            chat_id,
        )
        if not row:
            return None
        return dict(row)


async def clear_active_spawn(chat_id: int) -> None:
    """Remove the active spawn after claim or expiry."""
    redis = get_redis()
    await redis.delete(f"spawn:{chat_id}")
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM active_spawns WHERE chat_id = $1", chat_id)

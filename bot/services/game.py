"""High-level game operations: claim, gift, trade, favorite."""
from __future__ import annotations

import time
from dataclasses import dataclass

from bot.db.pool import get_pool


@dataclass
class ClaimResult:
    success: bool
    reason: str = ""
    character_id: int = 0
    name: str = ""
    anime: str = ""
    rarity: str = ""
    rarity_score: int = 0


async def claim_character(*, chat_id: int, user_id: int, username: str,
                          full_name: str, spawn: dict) -> ClaimResult:
    """Atomically claim a spawned character for a user.

    Uses SELECT ... FOR UPDATE on the active spawn row to prevent races
    when multiple users /guess at the same instant.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the spawn row
            row = await conn.fetchrow(
                "SELECT character_id, expires_at FROM active_spawns "
                "WHERE chat_id = $1 FOR UPDATE",
                chat_id,
            )
            if not row:
                return ClaimResult(success=False, reason="no_active_spawn")

            now = int(time.time())
            if row["expires_at"] < now:
                await conn.execute("DELETE FROM active_spawns WHERE chat_id = $1", chat_id)
                return ClaimResult(success=False, reason="expired")

            char_id = row["character_id"]

            # Upsert user
            await conn.execute(
                """
                INSERT INTO users (user_id, username, full_name, last_seen_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                  username = EXCLUDED.username,
                  full_name = EXCLUDED.full_name,
                  last_seen_at = NOW()
                """,
                user_id, username, full_name,
            )

            # Insert into harem (UNIQUE constraint prevents double-claim by same user)
            try:
                await conn.execute(
                    """
                    INSERT INTO harem (user_id, chat_id, character_id)
                    VALUES ($1, $2, $3)
                    """,
                    user_id, chat_id, char_id,
                )
            except Exception:
                return ClaimResult(
                    success=False, reason="already_owned",
                    character_id=char_id,
                )

            # Update aggregates
            char = await conn.fetchrow(
                "SELECT name, anime, rarity, rarity_score FROM characters WHERE id = $1",
                char_id,
            )
            await conn.execute(
                """
                INSERT INTO user_group_stats (user_id, chat_id, claims, rarity_score)
                VALUES ($1, $2, 1, $3)
                ON CONFLICT (user_id, chat_id) DO UPDATE SET
                  claims = user_group_stats.claims + 1,
                  rarity_score = user_group_stats.rarity_score + EXCLUDED.rarity_score
                """,
                user_id, chat_id, char["rarity_score"],
            )
            await conn.execute(
                """
                INSERT INTO users (user_id, total_claims, highest_rarity)
                VALUES ($1, 1, $2)
                ON CONFLICT (user_id) DO UPDATE SET
                  total_claims = users.total_claims + 1,
                  highest_rarity = COALESCE(
                    NULLIF(users.highest_rarity, '') = '', FALSE
                  ) AND TRUE OR users.highest_rarity
                """,
                user_id, char["rarity"],
            )
            await conn.execute(
                "UPDATE group_stats SET total_claims = total_claims + 1 WHERE chat_id = $1",
                chat_id,
            )

            # Remove active spawn
            await conn.execute("DELETE FROM active_spawns WHERE chat_id = $1", chat_id)

            return ClaimResult(
                success=True,
                character_id=char_id,
                name=char["name"],
                anime=char["anime"],
                rarity=char["rarity"],
                rarity_score=char["rarity_score"],
            )


async def get_user_harem(user_id: int, chat_id: int, limit: int = 50) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT h.acquired_at, h.is_favorite, c.id, c.name, c.anime,
                   c.rarity, c.rarity_score, c.image_url, c.description
            FROM harem h
            JOIN characters c ON c.id = h.character_id
            WHERE h.user_id = $1 AND h.chat_id = $2
            ORDER BY h.is_favorite DESC, c.rarity_score DESC
            LIMIT $3
            """,
            user_id, chat_id, limit,
        )
        return [dict(r) for r in rows]


async def set_favorite(user_id: int, chat_id: int, character_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        # Unset any previous favorite in this chat
        await conn.execute(
            "UPDATE harem SET is_favorite = FALSE "
            "WHERE user_id = $1 AND chat_id = $2 AND is_favorite = TRUE",
            user_id, chat_id,
        )
        result = await conn.execute(
            "UPDATE harem SET is_favorite = TRUE "
            "WHERE user_id = $1 AND chat_id = $2 AND character_id = $3",
            user_id, chat_id, character_id,
        )
        return result.endswith("1")  # "UPDATE 1"


async def gift_character(from_uid: int, to_uid: int, chat_id: int,
                         character_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id FROM harem WHERE user_id = $1 AND chat_id = $2 AND character_id = $3 "
                "AND is_favorite = FALSE FOR UPDATE",
                from_uid, chat_id, character_id,
            )
            if not row:
                return False
            await conn.execute(
                "DELETE FROM harem WHERE id = $1", row["id"],
            )
            await conn.execute(
                """
                INSERT INTO harem (user_id, chat_id, character_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, chat_id, character_id) DO NOTHING
                """,
                to_uid, chat_id, character_id,
            )
            # Update aggregate stats
            await conn.execute(
                "UPDATE user_group_stats SET claims = claims - 1, rarity_score = rarity_score - $4 "
                "WHERE user_id = $1 AND chat_id = $2",
                from_uid, chat_id, _rarity_score_of(conn, character_id),
            )
            return True


async def _rarity_score_of(conn, character_id: int) -> int:
    row = await conn.fetchrow("SELECT rarity_score FROM characters WHERE id = $1", character_id)
    return row["rarity_score"] if row else 0


async def create_trade(*, chat_id: int, from_uid: int, to_uid: int,
                       from_char: int, to_char: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO trades (chat_id, from_user_id, to_user_id,
                                from_character_id, to_character_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            chat_id, from_uid, to_uid, from_char, to_char,
        )
        return row["id"]


async def accept_trade(trade_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            t = await conn.fetchrow(
                "SELECT * FROM trades WHERE id = $1 AND status = 'pending' FOR UPDATE",
                trade_id,
            )
            if not t:
                return False
            # Verify both still own their chars
            from_own = await conn.fetchval(
                "SELECT id FROM harem WHERE user_id=$1 AND character_id=$2 AND chat_id=$3 AND is_favorite=FALSE",
                t["from_user_id"], t["from_character_id"], t["chat_id"],
            )
            to_own = await conn.fetchval(
                "SELECT id FROM harem WHERE user_id=$1 AND character_id=$2 AND chat_id=$3 AND is_favorite=FALSE",
                t["to_user_id"], t["to_character_id"], t["chat_id"],
            )
            if not (from_own and to_own):
                await conn.execute("UPDATE trades SET status='failed', resolved_at=NOW() WHERE id=$1", trade_id)
                return False
            # Swap
            await conn.execute("DELETE FROM harem WHERE id IN ($1, $2)", from_own, to_own)
            await conn.execute(
                "INSERT INTO harem (user_id, chat_id, character_id) VALUES ($1,$2,$3)",
                t["to_user_id"], t["chat_id"], t["from_character_id"],
            )
            await conn.execute(
                "INSERT INTO harem (user_id, chat_id, character_id) VALUES ($1,$2,$3)",
                t["from_user_id"], t["chat_id"], t["to_character_id"],
            )
            await conn.execute(
                "UPDATE trades SET status='accepted', resolved_at=NOW() WHERE id=$1",
                trade_id,
            )
            return True


async def get_leaderboard_global(limit: int = 10) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.user_id, u.username, u.full_name,
                   u.total_claims, u.highest_rarity
            FROM users u
            ORDER BY u.total_claims DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


async def get_leaderboard_chat(chat_id: int, limit: int = 10) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.user_id, u.username, u.full_name,
                   s.claims, s.rarity_score
            FROM user_group_stats s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.chat_id = $1
            ORDER BY s.rarity_score DESC, s.claims DESC
            LIMIT $2
            """,
            chat_id, limit,
        )
        return [dict(r) for r in rows]


async def get_leaderboard_groups(limit: int = 10) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.chat_id, g.title, g.username,
                   COALESCE(s.total_spawns, 0) AS spawns,
                   COALESCE(s.total_claims, 0) AS claims
            FROM groups g
            LEFT JOIN group_stats s ON s.chat_id = g.chat_id
            WHERE g.enabled = TRUE
            ORDER BY s.total_claims DESC NULLS LAST
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]

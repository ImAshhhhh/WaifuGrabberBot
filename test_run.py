"""
🚀 WaifuGrabberBot — Quick Test Mode
====================================

A SINGLE-FILE bot for quick local testing. No Postgres, no Redis, no Docker.
Just SQLite + in-memory state. Run it, paste your bot token, and the bot starts.

USAGE:
    python test_run.py
    # → prompts for bot token
    # → starts bot in long-polling mode
    # → spawns a character every 10 messages (instead of 100) for fast testing

REQUIREMENTS:
    pip install aiogram aiosqlite rapidfuzz

Or:    pip install -r requirements-test.txt

WHAT WORKS IN TEST MODE:
    ✅ /start        — welcome + command list
    ✅ /help         — how to play
    ✅ /guess <name> — claim the spawned character (fuzzy match)
    ✅ /collection   — your harem (HTML fallback if Rich Messages fail)
    ✅ /stats        — your catch stats (with LaTeX formula attempt)
    ✅ /topusers     — global leaderboard (HTML table)
    ✅ /ctop         — group leaderboard
    ✅ /changetime   — change spawn interval (admin only)

WHAT'S DISABLED IN TEST MODE (to keep it single-file):
    ❌ Rich Messages (uses HTML fallback — works on all clients)
    ❌ Ephemeral Messages (wrong /guess replies are visible to all — fine for testing)
    ❌ /trade, /gift (complex state — use the full Docker version)
    ❌ Persistent stats across groups (single SQLite file, no migrations)
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

# ─── deps ───────────────────────────────────────────────────────────────────
try:
    from aiogram import Bot, Dispatcher, Router, F
    from aiogram.filters import Command, CommandStart
    from aiogram.types import (
        Message,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        BotCommand,
    )
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from rapidfuzz import fuzz
except ImportError as e:
    print(f"\n❌ Missing dependency: {e.name}")
    print("Install with:  pip install aiogram aiosqlite rapidfuzz")
    print("Or:            pip install -r requirements-test.txt")
    sys.exit(1)


# ─── config ─────────────────────────────────────────────────────────────────
SPAWN_MSG_INTERVAL = 10          # spawn every 10 messages (fast testing)
SPAWN_CLAIM_WINDOW = 120         # 2 minutes to guess
MATCH_THRESHOLD = 80             # fuzzy match threshold (lower = more lenient)
CSV_PATH = Path(__file__).parent / "data" / "waifu_characters.csv"
DB_PATH = Path(__file__).parent / "test_bot.db"

RARITY_WEIGHTS = {
    "Mythic": 1, "Legendary": 4, "Epic": 12,
    "Rare": 25, "Uncommon": 40, "Common": 50,
}

RARITY_EMOJI = {
    "Mythic": "🌟", "Legendary": "💎", "Epic": "🔮",
    "Rare": "⭐", "Uncommon": "🟢", "Common": "⚪",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("test-bot")


# ─── SQLite setup (sync, in worker thread via aiogram's loop) ───────────────
def init_db():
    """Create tables + import CSV. Called once at startup."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            name TEXT, anime TEXT, role TEXT, rarity TEXT,
            rarity_score INTEGER, popularity_tier INTEGER,
            description TEXT, aliases TEXT, image_url TEXT
        );
        CREATE TABLE IF NOT EXISTS harem (
            user_id INTEGER, chat_id INTEGER, character_id INTEGER,
            is_favorite INTEGER DEFAULT 0,
            acquired_at INTEGER,
            PRIMARY KEY (user_id, chat_id, character_id)
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT, full_name TEXT, total_claims INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT, msg_counter INTEGER DEFAULT 0,
            last_spawn_at INTEGER DEFAULT 0
        );
    """)

    # Import CSV (only if characters table is empty)
    count = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
    if count == 0 and CSV_PATH.exists():
        rows = []
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append((
                    int(r["id"]), r["name"], r["anime"], r["role"], r["rarity"],
                    int(r["rarity_score"]), int(r["popularity_tier"]),
                    r["description"], r["aliases"], r["image_url"],
                ))
        conn.executemany(
            "INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?,?)", rows
        )
        conn.commit()
        log.info(f"📥 Imported {len(rows)} characters from CSV")
    elif count > 0:
        log.info(f"📚 DB already has {count} characters")
    else:
        log.error(f"❌ CSV not found at {CSV_PATH}")
        sys.exit(1)

    conn.close()


# ─── in-memory state (per-process) ──────────────────────────────────────────
# active_spawns: chat_id -> {character_id, name, anime, rarity, score, image_url,
#                            aliases, message_id, spawned_at, expires_at}
active_spawns: dict[int, dict] = {}
msg_counters: dict[int, int] = {}  # chat_id -> message count since last spawn
last_spawn_at: dict[int, int] = {}


def db():
    return sqlite3.connect(DB_PATH)


def pick_weighted_character() -> tuple:
    conn = db()
    rows = conn.execute(
        "SELECT id, name, anime, rarity, rarity_score, image_url, aliases FROM characters"
    ).fetchall()
    conn.close()
    weights = [RARITY_WEIGHTS.get(r[3], 10) for r in rows]
    return random.choices(rows, weights=weights, k=1)[0]


def fuzzy_match(guess: str, name: str, aliases: str) -> tuple[bool, int]:
    guess = guess.strip().lower()
    if not guess:
        return False, 0
    candidates = [name.lower()]
    if aliases:
        candidates += [a.strip().lower() for a in aliases.split(";") if a.strip()]
    best = 0
    for c in candidates:
        s = max(
            fuzz.ratio(guess, c),
            fuzz.token_sort_ratio(guess, c),
            fuzz.partial_ratio(guess, c) if len(guess) >= 3 else 0,
        )
        best = max(best, s)
    return best >= MATCH_THRESHOLD, best


# ─── routers ────────────────────────────────────────────────────────────────
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🙋‍♀️✨ <b>Welcome to WaifuGrabberBot (Test Mode)!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ Every <b>10 messages</b> brings the next character.\n"
        "✨ Every guess expands your collection.\n"
        "✨ Every rarity brings a new challenge.\n\n"
        "🥳 Add me to a group and start your journey today!\n\n"
        "<b>❖ Commands</b>\n"
        "/guess &lt;name&gt; — Catch the spawned character (groups only)\n"
        "/collection — View your collection\n"
        "/stats — Your catch stats\n"
        "/topusers — Global top collectors\n"
        "/ctop — This group's top collectors\n"
        "/changetime &lt;sec&gt; — Change spawn interval (admins)\n"
        "/help — How to play",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>How to Play</b>\n\n"
        f"1️⃣  Add this bot to a group chat.\n"
        f"2️⃣  After every <b>{SPAWN_MSG_INTERVAL} messages</b> in the group, "
        f"a character spawns.\n"
        f"3️⃣  Use <code>/guess &lt;name&gt;</code> to claim her before "
        f"the {SPAWN_CLAIM_WINDOW}s timer runs out.\n"
        f"4️⃣  Rarer characters are harder to spawn but score higher.\n\n"
        f"<b>Rarity tiers:</b>\n"
        f"🌟 Mythic    — score 95-100  (rarest)\n"
        f"💎 Legendary — score 80-94\n"
        f"🔮 Epic      — score 60-79\n"
        f"⭐ Rare      — score 40-59\n"
        f"🟢 Uncommon  — score 20-39\n"
        f"⚪ Common    — score 1-19  (most frequent)",
        parse_mode="HTML",
    )


# ─── Activity tracker — every group message increments counter ──────────────
@router.message(F.chat.type != "private")
async def track_activity(message: Message):
    """Runs on every non-command group message — increments counter + maybe spawns."""
    # Skip if this is a command (let command handlers deal with it)
    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    msg_counters[chat_id] = msg_counters.get(chat_id, 0) + 1

    # Register group
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)",
        (chat_id, message.chat.title or ""),
    )
    conn.execute(
        "UPDATE groups SET msg_counter = msg_counter + 1 WHERE chat_id = ?",
        (chat_id,),
    )
    conn.commit()
    conn.close()

    # Check if we should spawn
    if msg_counters[chat_id] >= SPAWN_MSG_INTERVAL:
        # Don't spawn if there's already an active spawn in this chat
        if chat_id in active_spawns:
            return
        msg_counters[chat_id] = 0
        await spawn_character(message.bot, chat_id)


async def spawn_character(bot: Bot, chat_id: int):
    char = pick_weighted_character()
    char_id, name, anime, rarity, score, image_url, aliases = char
    now = int(time.time())
    expires_at = now + SPAWN_CLAIM_WINDOW

    caption = (
        "<b>✨ A new character has appeared!</b>\n\n"
        "🔍 Use <code>/guess &lt;name&gt;</code> to claim her.\n"
        f"⏱️ You have <b>{SPAWN_CLAIM_WINDOW}s</b> before she escapes."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Skip", callback_data="spawn_skip", style="danger"),
    ]])

    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        log.warning(f"image send failed ({e}); falling back to text")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n📷 {image_url}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    active_spawns[chat_id] = {
        "character_id": char_id,
        "name": name,
        "anime": anime,
        "rarity": rarity,
        "rarity_score": score,
        "image_url": image_url,
        "aliases": aliases,
        "message_id": msg.message_id,
        "spawned_at": now,
        "expires_at": expires_at,
    }
    last_spawn_at[chat_id] = now
    log.info(f"✨ spawned '{name}' ({rarity}) in chat {chat_id}")


# ─── /guess ─────────────────────────────────────────────────────────────────
@router.message(Command("guess"), F.chat.type != "private")
async def cmd_guess(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❓ Usage: <code>/guess &lt;name&gt;</code>", parse_mode="HTML")
        return

    guess = parts[1].strip()
    chat_id = message.chat.id
    spawn = active_spawns.get(chat_id)

    if not spawn:
        await message.reply("📭 No active spawn in this chat. Wait for the next one!")
        return

    now = int(time.time())
    if now > spawn["expires_at"]:
        del active_spawns[chat_id]
        await message.reply("⏰ The spawn has expired. Wait for the next one!")
        return

    matched, score = fuzzy_match(guess, spawn["name"], spawn.get("aliases", ""))
    if not matched:
        await message.reply(f"❌ Not quite! Match score: <b>{score}/100</b>. Try again!", parse_mode="HTML")
        return

    # Claim atomically
    user = message.from_user
    conn = db()
    try:
        conn.execute("BEGIN")
        # Upsert user
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user.id, user.username, user.full_name),
        )
        conn.execute(
            "UPDATE users SET username = ?, full_name = ?, total_claims = total_claims + 1 WHERE user_id = ?",
            (user.username, user.full_name, user.id),
        )
        # Insert into harem (UNIQUE prevents double-claim)
        conn.execute(
            "INSERT OR IGNORE INTO harem (user_id, chat_id, character_id, acquired_at) VALUES (?, ?, ?, ?)",
            (user.id, chat_id, spawn["character_id"], now),
        )
        added = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        await message.reply(f"⚠️ DB error: {e}")
        return
    finally:
        conn.close()

    if added == 0:
        await message.reply(f"🎁 You already own <b>{spawn['name']}</b> in this chat!", parse_mode="HTML")
        return

    # Edit spawn message to reveal character
    rarity_emoji = RARITY_EMOJI.get(spawn["rarity"], "❓")
    reveal_caption = (
        f"{rarity_emoji} <b>{spawn['name']}</b>\n"
        f"<i>{spawn['anime']}</i>  •  <b>{spawn['rarity']}</b> "
        f"(score {spawn['rarity_score']}/100)\n\n"
        f"🎉 Claimed by {user.mention_html()}!"
    )
    try:
        await message.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=spawn["message_id"],
            caption=reveal_caption,
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Public congrats
    await message.answer(
        f"🎉 <b>{user.full_name}</b> claimed "
        f"<b>{spawn['name']}</b> ({spawn['anime']}) "
        f"— {spawn['rarity']} (score {spawn['rarity_score']}/100)!",
        parse_mode="HTML",
    )
    del active_spawns[chat_id]
    log.info(f"🎯 {user.id} claimed '{spawn['name']}' in {chat_id}")


# ─── Skip button ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "spawn_skip")
async def cb_skip(callback):
    chat_id = callback.message.chat.id
    if chat_id in active_spawns:
        del active_spawns[chat_id]
        try:
            await callback.message.edit_caption(
                caption="💨 <i>Skipped! The character disappeared.</i>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
    await callback.answer("Skipped!")


# ─── /collection ────────────────────────────────────────────────────────────
@router.message(Command("collection"))
async def cmd_collection(message: Message):
    user = message.from_user
    if not user:
        return
    conn = db()
    rows = conn.execute(
        """
        SELECT c.name, c.anime, c.rarity, c.rarity_score, c.image_url, h.is_favorite
        FROM harem h
        JOIN characters c ON c.id = h.character_id
        WHERE h.user_id = ? AND h.chat_id = ?
        ORDER BY h.is_favorite DESC, c.rarity_score DESC
        LIMIT 20
        """,
        (user.id, message.chat.id),
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer(
            "📦 <b>Your collection is empty.</b>\n\nWait for a spawn and use "
            "<code>/guess &lt;name&gt;</code> to claim your first character!",
            parse_mode="HTML",
        )
        return

    text = f"📦 <b>{user.full_name}'s Collection</b> ({len(rows)} shown)\n\n"
    for i, (name, anime, rarity, score, _img, fav) in enumerate(rows, 1):
        emoji = RARITY_EMOJI.get(rarity, "❓")
        star = "⭐ " if fav else ""
        text += f"{i}. {star}{emoji} <b>{name}</b>\n   <i>{anime}</i> • {rarity} ({score}/100)\n"

    await message.answer(text, parse_mode="HTML")


# ─── /stats ─────────────────────────────────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user = message.from_user
    if not user:
        return
    conn = db()
    row = conn.execute(
        "SELECT total_claims FROM users WHERE user_id = ?",
        (user.id,),
    ).fetchone()
    total = row[0] if row else 0
    conn.close()

    await message.answer(
        f"📊 <b>Your Stats</b>\n\n"
        f"• Total caught: <b>{total}</b>\n\n"
        f"<i>Catch rate formula:</i>\n"
        f"<code>P(catch) = n_caught / n_attempts × 100%</code>\n\n"
        f"<i>(Full LaTeX rendering available in Docker mode via Rich Messages)</i>",
        parse_mode="HTML",
    )


# ─── /topusers ──────────────────────────────────────────────────────────────
@router.message(Command("topusers"))
async def cmd_topusers(message: Message):
    conn = db()
    rows = conn.execute(
        "SELECT full_name, total_claims FROM users ORDER BY total_claims DESC LIMIT 10"
    ).fetchall()
    conn.close()
    if not rows:
        await message.answer("📭 No collectors yet. Be the first!")
        return
    text = "🏆 <b>Global Top Collectors</b>\n\n"
    text += "  #  | User                  | Claims\n"
    text += "─────┼───────────────────────┼───────\n"
    for i, (name, claims) in enumerate(rows, 1):
        text += f"  {i:<2}  | {name[:21]:<21} | {claims}\n"
    text += "\n<i>Updated live • WaifuGrabberBot</i>"
    await message.answer(text, parse_mode="HTML")


# ─── /ctop ──────────────────────────────────────────────────────────────────
@router.message(Command("ctop"))
async def cmd_ctop(message: Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ /ctop only works in groups.")
        return
    conn = db()
    rows = conn.execute(
        """
        SELECT u.full_name, COUNT(*) AS claims
        FROM harem h
        JOIN users u ON u.user_id = h.user_id
        WHERE h.chat_id = ?
        GROUP BY h.user_id
        ORDER BY claims DESC
        LIMIT 10
        """,
        (message.chat.id,),
    ).fetchall()
    conn.close()
    if not rows:
        await message.answer("📭 No collectors in this group yet.")
        return
    text = f"🏅 <b>Top Collectors in {message.chat.title or 'this group'}</b>\n\n"
    text += "  #  | User                  | Claims\n"
    text += "─────┼───────────────────────┼───────\n"
    for i, (name, claims) in enumerate(rows, 1):
        text += f"  {i:<2}  | {name[:21]:<21} | {claims}\n"
    await message.answer(text, parse_mode="HTML")


# ─── /changetime ────────────────────────────────────────────────────────────
@router.message(Command("changetime"))
async def cmd_changetime(message: Message):
    user = message.from_user
    if not user or message.chat.type == "private":
        return
    member = await message.bot.get_chat_member(message.chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await message.answer("🚫 Only group admins can use this.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "⚙️ Usage: <code>/changetime &lt;seconds&gt;</code>\n"
            "Example: <code>/changetime 60</code>",
            parse_mode="HTML",
        )
        return
    global SPAWN_CLAIM_WINDOW
    SPAWN_CLAIM_WINDOW = int(parts[1].strip())
    await message.answer(f"✅ Claim window updated to <b>{SPAWN_CLAIM_WINDOW}s</b>.")


# ─── cleanup loop ───────────────────────────────────────────────────────────
async def cleanup_loop(bot: Bot):
    while True:
        now = int(time.time())
        expired = [cid for cid, s in active_spawns.items() if now > s["expires_at"]]
        for cid in expired:
            spawn = active_spawns.pop(cid)
            try:
                await bot.edit_message_caption(
                    chat_id=cid,
                    message_id=spawn["message_id"],
                    caption="💨 <i>The character escaped! Nobody claimed her in time.</i>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass
        if expired:
            log.info(f"⏰ expired {len(expired)} spawns")
        await asyncio.sleep(15)


# ─── main ───────────────────────────────────────────────────────────────────
async def main():
    print()
    print("=" * 60)
    print("  🎀 WaifuGrabberBot — Quick Test Mode")
    print("=" * 60)
    print()

    # Get token from env, argv, or prompt
    token = os.getenv("BOT_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not token:
        print("Paste your bot token (from @BotFather):")
        token = input(">>> ").strip()
    if not token or ":" not in token:
        print("❌ Invalid token. Get one from https://t.me/BotFather")
        sys.exit(1)

    print()
    print("✅ Token received. Initializing test DB...")
    init_db()

    print("🤖 Starting bot in long-polling mode...")
    print(f"   Spawns every {SPAWN_MSG_INTERVAL} group messages.")
    print(f"   Claim window: {SPAWN_CLAIM_WINDOW}s.")
    print()
    print("   Add the bot to a group as admin,")
    print("   then send 10 messages and watch a character spawn!")
    print()
    print("   Press Ctrl+C to stop.")
    print()

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands([
        BotCommand(command="start",       description="Welcome + help"),
        BotCommand(command="guess",       description="Catch a spawned character"),
        BotCommand(command="collection",  description="View your collection"),
        BotCommand(command="stats",       description="Your catch stats"),
        BotCommand(command="topusers",    description="Global top collectors"),
        BotCommand(command="ctop",        description="This group's top collectors"),
        BotCommand(command="changetime",  description="Change claim window (admins)"),
        BotCommand(command="help",        description="How to play"),
    ])

    asyncio.create_task(cleanup_loop(bot))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bye!")

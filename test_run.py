"""
🚀 WaifuGrabberBot — Quick Test Mode (v2)
==========================================

Major upgrade:
  • Uses Rich Messages (Bot API 10.1) with LaTeX math blocks
  • Colored inline buttons on /start and admin panel
  • Time-based auto-spawn (every 10 minutes by default)
  • Admin panel for the bot owner (ID 7269251740)
  • Pre-seeds admin's collection with 10 characters
  • /guess always replies with right/wrong feedback
  • No skip button — spawns auto-expire when next one fires
  • Empty leaderboards still render a Rich Message table
  • Auto-falls back to HTML if Rich Messages aren't supported

USAGE:
    python test_run.py
    # → prompts for bot token

    BOT_TOKEN=123:ABC python test_run.py
    python test_run.py 123:ABC
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
    print("Install with:  pip install -r requirements-test.txt")
    sys.exit(1)


# ─── config ─────────────────────────────────────────────────────────────────
ADMIN_ID = 7269251740            # bot owner — gets admin panel + pre-seeded collection
SPAWN_INTERVAL_MIN = 10          # spawn every N minutes (time-based, universal)
SPAWN_CLAIM_WINDOW = 600         # spawn lives 10 minutes (until next one fires)
MATCH_THRESHOLD = 80             # fuzzy match threshold
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


# ═══════════════════════════════════════════════════════════════════════════
# RICH MESSAGE BUILDERS — Bot API 10.1
# ═══════════════════════════════════════════════════════════════════════════

def rt_plain(t: str):   return {"type": "plain", "text": t}
def rt_bold(t: str):    return {"type": "bold", "text": t}
def rt_italic(t: str):  return {"type": "italic", "text": t}
def rt_under(t: str):   return {"type": "underline", "text": t}
def rt_strike(t: str):  return {"type": "strikethrough", "text": t}
def rt_spoil(t: str):   return {"type": "spoiler", "text": t}
def rt_code(t: str):    return {"type": "code", "text": t}
def rt_marked(t: str):  return {"type": "marked", "text": t}
def rt_math(expr: str): return {"type": "mathematical_expression", "expression": expr, "format": "latex"}

def blk_heading(text: str):
    return {"type": "section_heading", "rich_text": [rt_plain(text)]}

def blk_footer(text: str):
    return {"type": "footer", "rich_text": [rt_italic(text)]}

def blk_divider():
    return {"type": "divider"}

def blk_paragraph(*items):
    return {"type": "paragraph", "rich_text": list(items)}

def blk_blockquote(*items):
    return {"type": "blockquote", "rich_text": list(items)}

def blk_list(items: list[list]):
    return {"type": "list", "items": [{"rich_text": it} for it in items]}

def blk_table(headers: list[str], rows: list[list[str]]):
    return {
        "type": "table",
        "header": [{"rich_text": [rt_plain(h)]} for h in headers],
        "rows": [[{"rich_text": [rt_plain(c)]} for c in row] for row in rows],
    }

def blk_math(expression: str):
    return {"type": "mathematical_expression", "expression": expression, "format": "latex"}


def blocks_to_html(blocks: list[dict]) -> str:
    """Fallback: render blocks as HTML for older clients."""
    out: list[str] = []
    for b in blocks:
        t = b.get("type")
        if t == "section_heading":
            out.append(f"<b>{_rich_to_html(b.get('rich_text', []))}</b>")
        elif t == "paragraph":
            out.append(_rich_to_html(b.get("rich_text", [])))
        elif t == "footer":
            out.append(f"<i>{_rich_to_html(b.get('rich_text', []))}</i>")
        elif t == "divider":
            out.append("━━━━━━━━━━━━━━━━━━━━")
        elif t == "blockquote":
            out.append(f"<blockquote>{_rich_to_html(b.get('rich_text', []))}</blockquote>")
        elif t == "list":
            for it in b.get("items", []):
                out.append(f"• {_rich_to_html(it.get('rich_text', []))}")
        elif t == "table":
            headers = b.get("header", [])
            rows = b.get("rows", [])
            if headers:
                h = " | ".join(_rich_to_html(h.get("rich_text", [])) for h in headers)
                out.append(f"<b>{h}</b>")
            for r in rows:
                out.append(" | ".join(_rich_to_html(c.get("rich_text", [])) for c in r))
        elif t == "mathematical_expression":
            out.append(f"<code>{b.get('expression', '')}</code>")
    return "\n".join(out)


def _rich_to_html(items):
    if isinstance(items, str):
        return items
    parts = []
    for it in items:
        t = it.get("type", "plain")
        text = it.get("text", "")
        if t == "bold":           parts.append(f"<b>{text}</b>")
        elif t == "italic":       parts.append(f"<i>{text}</i>")
        elif t == "underline":    parts.append(f"<u>{text}</u>")
        elif t == "strikethrough":parts.append(f"<s>{text}</s>")
        elif t == "spoiler":      parts.append(f"<tg-spoiler>{text}</tg-spoiler>")
        elif t == "code":         parts.append(f"<code>{text}</code>")
        elif t == "marked":       parts.append(f"<tg-spoiler>{text}</tg-spoiler>")
        elif t == "url":          parts.append(f'<a href="{it.get("url","")}">{text}</a>')
        elif t == "text_mention": parts.append(f'<a href="tg://user?id={it.get("user_id",0)}">{text}</a>')
        elif t == "mathematical_expression":
            parts.append(f"<code>{it.get('expression', '')}</code>")
        else:                     parts.append(text)
    return "".join(parts)


async def send_rich(bot: Bot, chat_id: int, blocks: list[dict], fallback: str | None = None):
    """Try Rich Messages first; fall back to HTML if not supported."""
    try:
        return await bot.send_rich_message(chat_id=chat_id, blocks=blocks)
    except Exception as e:
        log.debug(f"Rich message failed ({e}); using HTML fallback")
        html = fallback if fallback is not None else blocks_to_html(blocks)
        return await bot.send_message(chat_id=chat_id, text=html, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE (SQLite)
# ═══════════════════════════════════════════════════════════════════════════

def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db()
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
            title TEXT, last_spawn_at INTEGER DEFAULT 0
        );
    """)
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
        conn.executemany("INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        log.info(f"📥 Imported {len(rows)} characters from CSV")
    elif count > 0:
        log.info(f"📚 DB already has {count} characters")

    # Pre-seed admin's collection
    seed_admin_collection(conn)
    conn.close()


def seed_admin_collection(conn):
    """Give ADMIN_ID 10 random characters so /collection shows something on first run."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM harem WHERE user_id = ?", (ADMIN_ID,)
    ).fetchone()[0]
    if existing > 0:
        log.info(f"🌱 Admin already has {existing} characters")
        return
    # Pick 10 random chars across rarities — at least one of each tier
    picks = []
    for rarity in ["Mythic", "Legendary", "Epic", "Rare", "Uncommon", "Common"]:
        row = conn.execute(
            "SELECT id FROM characters WHERE rarity = ? ORDER BY RANDOM() LIMIT 1", (rarity,)
        ).fetchone()
        if row:
            picks.append(row[0])
    # Fill the rest with random
    while len(picks) < 10:
        row = conn.execute("SELECT id FROM characters ORDER BY RANDOM() LIMIT 1").fetchone()
        if row and row[0] not in picks:
            picks.append(row[0])

    now = int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name, total_claims) VALUES (?, ?, ?, ?)",
        (ADMIN_ID, "ashhhhh", "Ash (Owner)", len(picks)),
    )
    for char_id in picks:
        conn.execute(
            "INSERT OR IGNORE INTO harem (user_id, chat_id, character_id, acquired_at) VALUES (?, ?, ?, ?)",
            (ADMIN_ID, 0, char_id, now),
        )
    conn.commit()
    log.info(f"🌱 Seeded admin {ADMIN_ID} with {len(picks)} characters")


def pick_weighted_character():
    conn = db()
    rows = conn.execute(
        "SELECT id, name, anime, rarity, rarity_score, image_url, aliases, description FROM characters"
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


# ═══════════════════════════════════════════════════════════════════════════
# IN-MEMORY STATE
# ═══════════════════════════════════════════════════════════════════════════
active_spawns: dict[int, dict] = {}    # chat_id -> spawn info
last_spawn_at: dict[int, float] = {}   # chat_id -> last spawn timestamp
registered_groups: set[int] = set()    # chat_ids that we know about


# ═══════════════════════════════════════════════════════════════════════════
# SPAWN ENGINE (time-based)
# ═══════════════════════════════════════════════════════════════════════════

async def spawn_character(bot: Bot, chat_id: int, title: str = ""):
    """Spawn a character in the chat. Replaces any existing active spawn."""
    char = pick_weighted_character()
    char_id, name, anime, rarity, score, image_url, aliases, desc = char
    now = int(time.time())

    # If there's already an active spawn, expire it first
    if chat_id in active_spawns:
        old = active_spawns[chat_id]
        try:
            emoji = RARITY_EMOJI.get(old["rarity"], "❓")
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=old["message_id"],
                caption=f"💨 <i>Expired! The character was</i> {emoji} <b>{old['name']}</b>\n"
                        f"<i>{old['anime']}</i> • {old['rarity']}",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass

    caption = (
        "<b>✨ A new character has appeared!</b>\n\n"
        "🔍 Use <code>/guess &lt;name&gt;</code> to claim her.\n"
        f"⏱️ Next spawn in <b>{SPAWN_INTERVAL_MIN} min</b> — she vanishes then!"
    )
    # NO skip button — spawns auto-expire
    try:
        msg = await bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning(f"image send failed ({e}); falling back to text")
        msg = await bot.send_message(
            chat_id=chat_id,
            text=caption + f"\n\n📷 {image_url}",
            parse_mode="HTML",
        )

    active_spawns[chat_id] = {
        "character_id": char_id,
        "name": name, "anime": anime, "rarity": rarity,
        "rarity_score": score, "image_url": image_url,
        "aliases": aliases, "description": desc,
        "message_id": msg.message_id,
        "spawned_at": now,
    }
    last_spawn_at[chat_id] = now
    log.info(f"✨ spawned '{name}' ({rarity}) in chat {chat_id}")


async def auto_spawn_loop(bot: Bot):
    """Background task: spawn a character every SPAWN_INTERVAL_MIN minutes in every registered group."""
    while True:
        await asyncio.sleep(30)  # check every 30s
        now = time.time()
        for chat_id in list(registered_groups):
            last = last_spawn_at.get(chat_id, 0)
            if now - last >= SPAWN_INTERVAL_MIN * 60:
                try:
                    conn = db()
                    row = conn.execute("SELECT title FROM groups WHERE chat_id = ?", (chat_id,)).fetchone()
                    conn.close()
                    title = row[0] if row else ""
                    await spawn_character(bot, chat_id, title)
                except Exception as e:
                    log.warning(f"auto-spawn failed in {chat_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# ROUTERS / HANDLERS
# ═══════════════════════════════════════════════════════════════════════════
router = Router()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Colored main menu shown on /start."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Collection", callback_data="menu_collection", style="primary"),
            InlineKeyboardButton(text="📊 Stats",      callback_data="menu_stats",      style="success"),
        ],
        [
            InlineKeyboardButton(text="🏆 Top Users",  callback_data="menu_topusers",    style="primary"),
            InlineKeyboardButton(text="❓ Help",        callback_data="menu_help",        style="danger"),
        ],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    blocks = [
        blk_heading("🙋‍♀️✨ Welcome to WaifuGrabberBot!"),
        blk_paragraph(
            rt_plain("━━━━━━━━━━━━━━━━━━━━━━\n"),
            rt_plain("✨ Every "), rt_bold(f"{SPAWN_INTERVAL_MIN} minutes"),
            rt_plain(", a new character appears.\n"),
            rt_plain("✨ Every "), rt_bold("guess"),
            rt_plain(" expands your collection.\n"),
            rt_plain("✨ Every "), rt_bold("rarity"),
            rt_plain(" brings a new challenge."),
        ),
        blk_divider(),
        blk_paragraph(
            rt_plain("🥳 Add me to your group and start your journey today!\n\n"),
            rt_plain("Tap a button below 👇 or use commands directly."),
        ),
    ]
    await send_rich(message.bot, message.chat.id, blocks,
                    fallback="<b>🙋‍♀️✨ Welcome to WaifuGrabberBot!</b>\n\n"
                             f"✨ Every <b>{SPAWN_INTERVAL_MIN} minutes</b>, a new character appears.\n"
                             "✨ Every <b>guess</b> expands your collection.\n"
                             "✨ Every <b>rarity</b> brings a new challenge.\n\n"
                             "🥳 Add me to your group and start your journey today!")
    # Send the colored menu separately so it always shows
    await message.answer("👇 <b>Main Menu</b>", parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    blocks = [
        blk_heading("📖 How to Play"),
        blk_paragraph(
            rt_plain("1️⃣  Add this bot to a group chat.\n"),
            rt_plain("2️⃣  Every "), rt_bold(f"{SPAWN_INTERVAL_MIN} minutes"),
            rt_plain(", a character spawns automatically.\n"),
            rt_plain("3️⃣  Use "), rt_code("/guess <name>"),
            rt_plain(" to claim her before the next spawn.\n"),
            rt_plain("4️⃣  Rarer characters are harder to spawn but score higher."),
        ),
        blk_divider(),
        blk_paragraph(rt_bold("Rarity tiers:")),
        blk_list([
            [rt_plain("🌟 Mythic    — score 95-100  (rarest)")],
            [rt_plain("💎 Legendary — score 80-94")],
            [rt_plain("🔮 Epic      — score 60-79")],
            [rt_plain("⭐ Rare      — score 40-59")],
            [rt_plain("🟢 Uncommon  — score 20-39")],
            [rt_plain("⚪ Common    — score 1-19  (most frequent)")],
        ]),
        blk_divider(),
        blk_paragraph(rt_bold("Commands:")),
        blk_list([
            [rt_code("/guess <name>"), rt_plain(" — Catch the spawned character (groups only)")],
            [rt_code("/collection"),   rt_plain(" — View your collection")],
            [rt_code("/stats"),        rt_plain(" — Your catch stats")],
            [rt_code("/topusers"),     rt_plain(" — Global top collectors")],
            [rt_code("/ctop"),         rt_plain(" — This group's top collectors")],
            [rt_code("/changetime <min>"), rt_plain(" — Change spawn interval (admins)")],
            [rt_code("/admin"),        rt_plain(" — Owner's control panel")],
        ]),
    ]
    await send_rich(message.bot, message.chat.id, blocks)


# ─── Activity tracker — registers the group so auto-spawn can fire ─────────
@router.message(F.chat.type != "private")
async def track_activity(message: Message):
    """Register every group the bot sees so auto-spawn can target it."""
    if message.text and message.text.startswith("/"):
        return  # commands handled elsewhere
    chat_id = message.chat.id
    if chat_id not in registered_groups:
        registered_groups.add(chat_id)
        conn = db()
        conn.execute(
            "INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)",
            (chat_id, message.chat.title or ""),
        )
        conn.commit()
        conn.close()
        log.info(f"➕ registered group {chat_id} ({message.chat.title})")


# ─── /guess ────────────────────────────────────────────────────────────────
@router.message(Command("guess"), F.chat.type != "private")
async def cmd_guess(message: Message):
    user = message.from_user
    chat_id = message.chat.id

    # Make sure the group is registered (so auto-spawn will fire here)
    if chat_id not in registered_groups:
        registered_groups.add(chat_id)
        conn = db()
        conn.execute("INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)",
                     (chat_id, message.chat.title or ""))
        conn.commit()
        conn.close()

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❓ Usage: <code>/guess &lt;name&gt;</code>\n"
            "Example: <code>/guess hinata</code>",
            parse_mode="HTML",
        )
        return

    guess = parts[1].strip()
    spawn = active_spawns.get(chat_id)

    if not spawn:
        await message.reply(
            "📭 <b>No active spawn in this chat.</b>\n"
            f"Wait for the next one — spawns every <b>{SPAWN_INTERVAL_MIN} min</b>.",
            parse_mode="HTML",
        )
        return

    matched, score = fuzzy_match(guess, spawn["name"], spawn.get("aliases", ""))
    if not matched:
        await message.reply(
            f"❌ <b>Not quite!</b> Match score: <b>{score}/100</b>\n"
            f"Try again — she's still here!",
            parse_mode="HTML",
        )
        return

    # Atomic claim
    conn = db()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user.id, user.username, user.full_name),
        )
        conn.execute(
            "UPDATE users SET username = ?, full_name = ?, total_claims = total_claims + 1 WHERE user_id = ?",
            (user.username, user.full_name, user.id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO harem (user_id, chat_id, character_id, acquired_at) VALUES (?, ?, ?, ?)",
            (user.id, chat_id, spawn["character_id"], int(time.time())),
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
        await message.reply(
            f"🎁 <b>You already own {spawn['name']}!</b>\n"
            "Try catching the next character.",
            parse_mode="HTML",
        )
        return

    emoji = RARITY_EMOJI.get(spawn["rarity"], "❓")
    reveal = (
        f"{emoji} <b>{spawn['name']}</b>\n"
        f"<i>{spawn['anime']}</i>  •  <b>{spawn['rarity']}</b> "
        f"(score {spawn['rarity_score']}/100)\n\n"
        f"🎉 Claimed by {user.mention_html()}!"
    )
    try:
        await message.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=spawn["message_id"],
            caption=reveal,
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Rich Message congrats with LaTeX
    blocks = [
        blk_heading("🎉 Claimed!"),
        blk_paragraph(
            rt_bold(user.full_name),
            rt_plain(" caught "),
            rt_bold(spawn["name"]),
            rt_plain(" from "),
            rt_italic(spawn["anime"]),
            rt_plain("."),
        ),
        blk_blockquote(rt_plain(spawn["description"])),
        blk_paragraph(rt_plain("Rarity score:")),
        blk_math(rf"\text{{{spawn['rarity']}}} = \frac{{{spawn['rarity_score']}}}{{100}} \approx {spawn['rarity_score']/100:.2f}"),
    ]
    await send_rich(message.bot, chat_id, blocks,
                    fallback=f"🎉 <b>{user.full_name}</b> caught "
                             f"<b>{spawn['name']}</b> ({spawn['anime']}) — "
                             f"{spawn['rarity']} (score {spawn['rarity_score']}/100)!")
    del active_spawns[chat_id]
    log.info(f"🎯 {user.id} claimed '{spawn['name']}' in {chat_id}")


# ─── /collection ───────────────────────────────────────────────────────────
@router.message(Command("collection"))
async def cmd_collection(message: Message):
    user = message.from_user
    if not user:
        return
    conn = db()
    rows = conn.execute(
        """
        SELECT c.name, c.anime, c.rarity, c.rarity_score, h.is_favorite
        FROM harem h
        JOIN characters c ON c.id = h.character_id
        WHERE h.user_id = ? AND h.chat_id = ?
        ORDER BY h.is_favorite DESC, c.rarity_score DESC
        LIMIT 20
        """,
        (user.id, message.chat.id),
    ).fetchall()
    # Also check admin's "global" chat_id=0 stash if this user is the admin
    if user.id == ADMIN_ID and message.chat.type == "private":
        rows = conn.execute(
            """
            SELECT c.name, c.anime, c.rarity, c.rarity_score, h.is_favorite
            FROM harem h
            JOIN characters c ON c.id = h.character_id
            WHERE h.user_id = ? AND h.chat_id = 0
            ORDER BY h.is_favorite DESC, c.rarity_score DESC
            LIMIT 20
            """,
            (user.id,),
        ).fetchall()
    conn.close()

    if not rows:
        blocks = [
            blk_heading("📦 Your Collection"),
            blk_paragraph(
                rt_plain("Your harem is empty.\n\n"),
                rt_plain("Wait for a spawn in this group and use "),
                rt_code("/guess <name>"),
                rt_plain(" to claim your first character!"),
            ),
        ]
        await send_rich(message.bot, message.chat.id, blocks)
        return

    # Render as Rich Message table
    table_rows = []
    for i, (name, anime, rarity, score, fav) in enumerate(rows, 1):
        emoji = RARITY_EMOJI.get(rarity, "❓")
        star = "⭐ " if fav else ""
        table_rows.append([f"{i}", f"{star}{emoji} {name}", anime[:18], f"{score}"])

    blocks = [
        blk_heading(f"📦 {user.full_name}'s Collection"),
        blk_paragraph(rt_plain(f"Showing {len(rows)} characters.")),
        blk_table(["#", "Character", "Anime", "Score"], table_rows),
        blk_footer("Updated live • WaifuGrabberBot"),
    ]
    await send_rich(message.bot, message.chat.id, blocks)


# ─── /stats ─────────────────────────────────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user = message.from_user
    if not user:
        return
    conn = db()
    row = conn.execute(
        "SELECT total_claims FROM users WHERE user_id = ?", (user.id,)
    ).fetchone()
    total = row[0] if row else 0

    # Count unique characters in this chat
    char_count = conn.execute(
        "SELECT COUNT(*) FROM harem WHERE user_id = ? AND chat_id = ?",
        (user.id, message.chat.id),
    ).fetchone()[0]
    # For admin in DM, use chat_id=0
    if user.id == ADMIN_ID and message.chat.type == "private":
        char_count = conn.execute(
            "SELECT COUNT(*) FROM harem WHERE user_id = ? AND chat_id = 0",
            (user.id,),
        ).fetchone()[0]
    conn.close()

    blocks = [
        blk_heading("📊 Your Collection Stats"),
        blk_list([
            [rt_plain("Total caught: "), rt_bold(str(total))],
            [rt_plain("Unique characters: "), rt_bold(str(char_count))],
            [rt_plain("Spawn interval: "), rt_bold(f"{SPAWN_INTERVAL_MIN} min")],
        ]),
        blk_divider(),
        blk_paragraph(rt_plain("Catch rate formula:")),
        blk_math(r"P(\text{catch}) = \frac{n_{\text{caught}}}{n_{\text{attempts}}} \times 100\%"),
        blk_divider(),
        blk_paragraph(rt_italic("Tip: catch rarer characters to boost your score!")),
    ]
    await send_rich(message.bot, message.chat.id, blocks)


# ─── /topusers ──────────────────────────────────────────────────────────────
@router.message(Command("topusers"))
async def cmd_topusers(message: Message):
    conn = db()
    rows = conn.execute(
        "SELECT full_name, total_claims FROM users ORDER BY total_claims DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        # Empty leaderboard — STILL render a table with "no users" row
        table_rows = [["—", "No users currently on leaderboard", "—"]]
    else:
        table_rows = [
            [f"{i}", name[:24], f"{claims}"]
            for i, (name, claims) in enumerate(rows, 1)
        ]

    blocks = [
        blk_heading("🏆 Global Top Collectors"),
        blk_table(["#", "User", "Claims"], table_rows),
        blk_footer("Updated live • WaifuGrabberBot"),
    ]
    await send_rich(message.bot, message.chat.id, blocks)


# ─── /ctop ──────────────────────────────────────────────────────────────────
@router.message(Command("ctop"))
async def cmd_ctop(message: Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ <code>/ctop</code> only works in groups.", parse_mode="HTML")
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
        table_rows = [["—", "No users currently on leaderboard", "—"]]
    else:
        table_rows = [
            [f"{i}", name[:24], f"{claims}"]
            for i, (name, claims) in enumerate(rows, 1)
        ]

    title = message.chat.title or "this group"
    blocks = [
        blk_heading(f"🏅 Top Collectors in {title}"),
        blk_table(["#", "User", "Claims"], table_rows),
        blk_footer("Updated live • WaifuGrabberBot"),
    ]
    await send_rich(message.bot, message.chat.id, blocks)


# ─── /changetime ────────────────────────────────────────────────────────────
@router.message(Command("changetime"))
async def cmd_changetime(message: Message):
    user = message.from_user
    if not user or message.chat.type == "private":
        return
    member = await message.bot.get_chat_member(message.chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await message.answer("🚫 Only group admins can use this.", parse_mode="HTML")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "⚙️ Usage: <code>/changetime &lt;minutes&gt;</code>\n"
            "Example: <code>/changetime 5</code>",
            parse_mode="HTML",
        )
        return
    global SPAWN_INTERVAL_MIN
    SPAWN_INTERVAL_MIN = max(1, min(1440, int(parts[1].strip())))
    await message.answer(
        f"✅ Spawn interval updated to <b>{SPAWN_INTERVAL_MIN} min</b> for this bot.",
        parse_mode="HTML",
    )


# ─── /admin — colorful admin panel for ADMIN_ID only ────────────────────────
def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏱️ Set Spawn Interval", callback_data="admin_setspawn", style="primary"),
            InlineKeyboardButton(text="📊 Bot Stats",           callback_data="admin_stats",   style="success"),
        ],
        [
            InlineKeyboardButton(text="🌱 Re-seed My Collection", callback_data="admin_seed",  style="primary"),
            InlineKeyboardButton(text="🧹 Clear All Spawns",     callback_data="admin_clear",  style="danger"),
        ],
        [
            InlineKeyboardButton(text="📣 Broadcast",             callback_data="admin_broadcast", style="primary"),
        ],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    user = message.from_user
    if not user or user.id != ADMIN_ID:
        await message.answer("🚫 <b>Access denied.</b> Only the bot owner can use this command.", parse_mode="HTML")
        return

    blocks = [
        blk_heading("🎛️ Admin Control Panel"),
        blk_paragraph(
            rt_plain("Welcome, "), rt_bold("Owner"),
            rt_plain(". Choose an action below 👇"),
        ),
        blk_divider(),
        blk_list([
            [rt_plain("👤 Your ID: "), rt_code(str(ADMIN_ID))],
            [rt_plain("⏱️ Current spawn interval: "), rt_bold(f"{SPAWN_INTERVAL_MIN} min")],
            [rt_plain("🌐 Registered groups: "), rt_bold(str(len(registered_groups)))],
            [rt_plain("✨ Active spawns: "), rt_bold(str(len(active_spawns)))],
        ]),
    ]
    await send_rich(message.bot, message.chat.id, blocks)
    await message.answer("👇 <b>Admin Actions</b>", parse_mode="HTML", reply_markup=admin_keyboard())


@router.callback_query(F.data.startswith("admin_"))
async def cb_admin(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Access denied", show_alert=True)
        return

    action = callback.data.split("_", 1)[1]
    if action == "stats":
        conn = db()
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        chars = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
        groups_db = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
        harem = conn.execute("SELECT COUNT(*) FROM harem").fetchone()[0]
        conn.close()
        blocks = [
            blk_heading("📊 Bot Statistics"),
            blk_list([
                [rt_plain("👥 Total users: "), rt_bold(str(users))],
                [rt_plain("📚 Character pool: "), rt_bold(str(chars))],
                [rt_plain("🌐 Registered groups: "), rt_bold(str(groups_db))],
                [rt_plain("💾 Total claims: "), rt_bold(str(harem))],
                [rt_plain("✨ Active spawns: "), rt_bold(str(len(active_spawns)))],
            ]),
            blk_divider(),
            blk_math(r"\text{engagement} = \frac{\text{claims}}{\text{users}} = \frac{" + str(harem) + r"}{" + str(users) + r"}"),
        ]
        await send_rich(callback.bot, callback.message.chat.id, blocks)
    elif action == "seed":
        conn = db()
        # Delete existing admin collection and re-seed
        conn.execute("DELETE FROM harem WHERE user_id = ?", (ADMIN_ID,))
        seed_admin_collection(conn)
        conn.close()
        await callback.message.answer("🌱 <b>Re-seeded!</b> Your collection now has 10 fresh characters.", parse_mode="HTML")
    elif action == "clear":
        n = len(active_spawns)
        active_spawns.clear()
        await callback.message.answer(f"🧹 Cleared <b>{n}</b> active spawns.", parse_mode="HTML")
    elif action == "setspawn":
        await callback.message.answer(
            "⏱️ Use the command to set spawn interval:\n"
            "<code>/changetime &lt;minutes&gt;</code>\n"
            "Example: <code>/changetime 5</code>",
            parse_mode="HTML",
        )
    elif action == "broadcast":
        await callback.message.answer(
            "📣 Broadcast feature:\n"
            "Use <code>/broadcast &lt;message&gt;</code> to send a message to all registered groups.",
            parse_mode="HTML",
        )
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    user = message.from_user
    if not user or user.id != ADMIN_ID:
        await message.answer("🚫 Access denied.", parse_mode="HTML")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: <code>/broadcast &lt;message&gt;</code>", parse_mode="HTML")
        return
    text = parts[1]
    sent, failed = 0, 0
    for chat_id in list(registered_groups):
        try:
            await message.bot.send_message(chat_id, f"📢 <b>Broadcast:</b>\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📣 Sent to {sent} groups ({failed} failed).", parse_mode="HTML")


# ─── Main menu callback handlers ────────────────────────────────────────────
@router.callback_query(F.data.startswith("menu_"))
async def cb_menu(callback: CallbackQuery):
    action = callback.data.split("_", 1)[1]
    # Reuse the command handlers by faking a message
    fake_msg = callback.message
    fake_msg.from_user = callback.from_user
    fake_msg.text = f"/{action}"
    if action == "collection":
        await cmd_collection(fake_msg)
    elif action == "stats":
        await cmd_stats(fake_msg)
    elif action == "topusers":
        await cmd_topusers(fake_msg)
    elif action == "help":
        await cmd_help(fake_msg)
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print()
    print("=" * 60)
    print("  🎀 WaifuGrabberBot — Quick Test Mode v2")
    print("=" * 60)
    print()

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
    print(f"🌱 Admin ID: {ADMIN_ID} (pre-seeded with 10 characters)")
    print(f"⏱️  Spawn interval: every {SPAWN_INTERVAL_MIN} minutes (time-based)")
    print()
    print("🤖 Starting bot in long-polling mode...")
    print()
    print("   ⚠️  IMPORTANT: Disable Group Privacy Mode in @BotFather:")
    print("      /mybots → your bot → Bot Settings → Group Privacy → Turn off")
    print("      Then remove + re-add the bot to your groups.")
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
        BotCommand(command="start",       description="Welcome + main menu"),
        BotCommand(command="guess",       description="Catch the spawned character"),
        BotCommand(command="collection",  description="View your collection"),
        BotCommand(command="stats",       description="Your catch stats"),
        BotCommand(command="topusers",    description="Global top collectors"),
        BotCommand(command="ctop",        description="This group's top collectors"),
        BotCommand(command="changetime",  description="Change spawn interval (admins)"),
        BotCommand(command="admin",       description="Owner control panel"),
        BotCommand(command="broadcast",   description="Broadcast to all groups (owner)"),
        BotCommand(command="help",        description="How to play"),
    ])

    # Load existing groups from DB so auto-spawn targets them
    conn = db()
    rows = conn.execute("SELECT chat_id, last_spawn_at FROM groups").fetchall()
    conn.close()
    for chat_id, last in rows:
        registered_groups.add(chat_id)
        if last:
            last_spawn_at[chat_id] = last
    log.info(f"🌐 Loaded {len(registered_groups)} groups from DB")

    asyncio.create_task(auto_spawn_loop(bot))

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

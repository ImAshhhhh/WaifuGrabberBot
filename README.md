<div align="center">

# 🎀 WaifuGrabberBot

### A high-performance Telegram waifu catcher bot — built on the latest Bot API 10.2

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.30-2CA5E0?logo=telegram&logoColor=white)
![Postgres](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-10.2-26A5E4?logo=telegram&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22C55E)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-FF69B4)

**Every message brings the next character. Every guess expands your collection. Every rarity brings a new challenge.**

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🎯 Core Gameplay
- ⚡ **Spawns every N messages** or every M seconds (whichever comes first)
- 🎲 **Weighted random** rarity pool — Mythics spawn ~1% of the time
- 🧠 **Fuzzy matching** — `"remu"` still catches `"Rem"` (rapidfuzz, threshold 85/100)
- ⏱️ **Auto-expiring spawns** — 90s claim window, then she escapes
- 🔒 **Atomic claims** — Postgres `SELECT ... FOR UPDATE` prevents race conditions when 5 users `/guess` at once

### 🎨 Latest Telegram API Features Used
- 🎨 **Colored inline buttons** — Bot API 9.4 `style` field (`success`/`danger`/`primary`)
- 📐 **LaTeX math blocks** — Bot API 10.1 `RichBlockMathematicalExpression` for catch-rate formulas
- 🖼️ **Slideshow collections** — Bot API 10.1 `RichBlockSlideshow` for the `/collection` view
- 📊 **Table leaderboards** — Bot API 10.1 `RichBlockTable` for `/topusers`, `/ctop`, `/topgroups`
- 👻 **Ephemeral Messages** — Bot API 10.2 — wrong `/guess` feedback visible only to the guesser (no group spam!)
- 📝 **Custom emoji buttons** — Bot API 9.4 `icon_custom_emoji_id` (Premium bots)

</td>
<td width="50%" valign="top">

### 🚀 Built for Scale (10k concurrent users)
- ⚡ **async/await** end-to-end (aiogram 3.30 + asyncpg + redis-py)
- 🗄️ **PostgreSQL 16** — concurrent writes, ACID guarantees, proper indexes
- 🟥 **Redis 7** — active spawn state, per-user throttling, leaderboards
- 🔄 **Connection pooling** — 10–30 Postgres connections, 50 Redis connections
- 🧠 **In-memory character cache** — weighted random with zero DB hits per spawn
- 🪶 **uvloop** — 2-4× faster event loop on Linux
- 🌐 **Webhook mode** — production-grade; long-polling for dev

### 📦 Commands (matches the demo welcome screen)

| Command | Where | Description |
|---|---|---|
| `/guess <name>` | Groups | Catch the spawned character |
| `/collection` | Anywhere | View your harem as a slideshow |
| `/fav <id>` | Anywhere | Mark a character as favorite |
| `/gift <id>` | Groups | Gift a character (reply to user) |
| `/trade <your> <their>` | Groups | Trade with another collector |
| `/topusers` | Anywhere | 🏆 Global top collectors (table) |
| `/ctop` | Groups | 🏅 This group's top collectors (table) |
| `/topgroups` | Anywhere | 🌐 Global top groups (table) |
| `/stats` | Anywhere | 📊 Your stats with LaTeX formula |
| `/changetime <sec>` | Admins | Change spawn interval |

</td>
</tr>
</table>

---

## 🎬 Demo

```
🎉 ✨ A new character has appeared!

🔍 Use /guess <name> to claim her.
⏱️ You have 90 seconds before she escapes.

[🎁 Claim Hint (blue)]   [❌ Skip (red)]
```

↓ after `/guess hinata`

```
🌟 Hinata Hyuga
Naruto  •  Mythic (score 95/100)

🎉 Claimed by @yourname!
```

↓ `/topusers` renders as a Rich Message table:

```
┌─────────────────────────────────────┐
│ 🏆 Global Top Collectors            │
├─────┬──────────────┬────────┬────────┤
│  #  │ User         │ Claims │ Best   │
├─────┼──────────────┼────────┼────────┤
│  1  │ alice        │   42   │ Mythic │
│  2  │ bob          │   38   │ Legend │
│  3  │ charlie      │   27   │ Epic   │
└─────┴──────────────┴────────┴────────┘
Updated live • WaifuGrabberBot
```

↓ `/collection` renders as a **slideshow** — swipe through your characters!

↓ `/stats` shows your catch rate with a real LaTeX formula:

```
📊 Your Collection Stats

• Total caught: 42
• Total attempts: 58
• Catch rate: 72.4%

Catch rate formula:

   P(catch) = (n_caught / n_attempts) × 100%
```

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Telegram (groups)                     │
└────────────────────────────┬─────────────────────────────┘
                             │  webhook OR long polling
                             ▼
┌──────────────────────────────────────────────────────────┐
│                  aiogram 3.30 Dispatcher                   │
│  ┌────────────────┐  ┌────────────────────────────────┐ │
│  │ Throttling MW  │→ │ Activity MW (msg counter)       │ │
│  │ (Redis cooldown)│  │ → maybe_spawn() weighted random │ │
│  └────────────────┘  └────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Routers: start / guess / collection / fav_gift  │   │
│  │           trade / leaderboards / admin / stats    │   │
│  └──────────────────────────────────────────────────┘   │
└──────────┬──────────────────────────────┬───────────────┘
           │                              │
   ┌───────▼────────┐            ┌───────▼────────┐
   │  PostgreSQL 16  │            │   Redis 7      │
   │  (asyncpg pool) │            │ (state + cache)│
   └─────────────────┘            └────────────────┘
```

---

## 🚀 Quick Start (Local Dev)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/WaifuGrabberBot.git
cd WaifuGrabberBot

# 2. Copy env
cp .env.example .env
# Edit .env — fill in BOT_TOKEN, OWNER_ID

# 3. Start Postgres + Redis
docker compose up -d postgres redis

# 4. Install deps + init DB
pip install -r requirements.txt
python -m bot.db.init_db   # creates schema + imports 508 characters from CSV

# 5. Run
python -m bot
```

For full VPS deployment (Nginx + HTTPS webhook + systemd), see **[deploy.md](deploy.md)**.

---

## ⚡ Quick Test Mode (No Docker, No Postgres, No Redis)

Want to test the bot right now without setting up anything? Use the single-file test mode — it uses SQLite + in-memory state and runs in long-polling.

```bash
# 1. Clone
git clone https://github.com/ImAshhhhh/WaifuGrabberBot.git
cd WaifuGrabberBot

# 2. Install minimal deps (just aiogram + rapidfuzz)
pip install -r requirements-test.txt

# 3. Run — it will prompt you for your bot token
python test_run.py
# >>> paste your token from @BotFather

# 4. Add the bot to a test group as admin.
# 5. Send 10 messages → a character spawns!
# 6. Use /guess <name> to claim her.
```

**Test mode features:**
- ✅ Spawns every **10 messages** (instead of 100) for fast iteration
- ✅ All core commands: `/start`, `/help`, `/guess`, `/collection`, `/stats`, `/topusers`, `/ctop`, `/changetime`
- ✅ Fuzzy name matching (rapidfuzz)
- ✅ Colored inline buttons (Bot API 9.4 `style` field)
- ✅ Auto-creates SQLite DB + imports the 508-character CSV on first run
- ⚠️ Falls back to HTML instead of Rich Messages (works on every Telegram client)
- ⚠️ Wrong `/guess` replies are public (no Ephemeral Messages in test mode)

You can also pass the token via env or argv to skip the prompt:

```bash
BOT_TOKEN=123:ABC python test_run.py
# or
python test_run.py 123:ABC
```

For full VPS deployment (Nginx + HTTPS webhook + systemd), see **[deploy.md](deploy.md)**.

---

## ☁️ Run via GitHub Actions (No VPS, No Local Install)

Want to run the bot temporarily without a VPS or local Python? Use the included GitHub Actions workflow — it spins up the bot on GitHub's servers for a set number of hours.

### 📋 One-Time Setup (Recommended)

1. Go to **Settings → Secrets and variables → Actions → New repository secret**
   - **Name:** `BOT_TOKEN`
   - **Value:** your bot token from @BotFather
2. This keeps your token private — even from workflow logs.

### ▶️ Trigger a Run

1. Go to the **Actions** tab in the repo.
2. Select **"🤖 Run WaifuGrabberBot (Timed)"** in the left sidebar.
3. Click **"Run workflow"** — a form appears:

   | Field | Description |
   |---|---|
   | `bot_token` | Paste your token (ignored if you check the secret box) |
   | `hours` | How long to run — 1 to 6 hours (GitHub free-tier limit) |
   | `spawn_interval` | Spawn every N messages (default 10 for fast testing) |
   | `use_secret` | ✅ Check this to use the `BOT_TOKEN` repo secret (recommended) |

4. Click **Run workflow**. The job takes ~30s to start.
5. Click into the running workflow → **"run-bot"** job → watch live logs of the bot starting up.

### ⚠️ Important Notes

- **GitHub free-tier limit:** a single job runs at most **6 hours** before being killed. If you need 24/7 uptime, deploy on a real VPS (see `deploy.md`).
- **Plaintext token warning:** if you don't check `use_secret`, your token appears in plaintext in the workflow run UI — visible to anyone with repo access. **Always prefer the secret option.**
- **Auto-cancel:** starting a new run cancels the previous one (so you don't run two bots on the same token — Telegram would disconnect one anyway).
- **Logs are uploaded as artifacts** at the end of every run (kept for 7 days).
- **Cleanup:** the workflow automatically deletes `bot.log`, `bot.pid`, and `test_bot.db` at the end — no secrets persist.

### 🧪 Quick Try (No Secret Setup)

If you just want to test for 1 hour without setting up a secret:

1. Actions tab → "🤖 Run WaifuGrabberBot (Timed)" → Run workflow
2. Paste token, hours=`1`, spawn_interval=`10`, use_secret=`false`
3. Click Run workflow
4. Watch the logs — add the bot to a group → send 10 messages → character spawns!

### ⚠️ CRITICAL: Disable Group Privacy Mode

By default, Telegram bots have **Group Privacy Mode ON**, which means they can only see:
- Messages that start with a `/command`
- Replies to the bot's own messages
- Messages in groups where the bot is an admin

For WaifuGrabberBot to count **every** group message (and spawn after 10/100 of them), you MUST disable privacy mode:

1. Open [@BotFather](https://t.me/BotFather)
2. Send `/mybots`
3. Choose your bot → **Bot Settings** → **Group Privacy**
4. Click **Turn off**
5. Remove the bot from any groups it's in, then re-add it (privacy changes don't apply retroactively)

You can verify it worked by calling getMe — `can_read_all_group_messages` should be `true`:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe" | jq .result.can_read_all_group_messages
```

---

## 🎨 Color & Button Cheatsheet

We use the new `style` field on every interactive button:

| Color | Style value | Use case |
|---|---|---|
| 🔵 Dark blue | `style="primary"` | Main actions (claim hint, favorite) |
| 🟢 Green | `style="success"` | Positive actions (accept trade, view collection) |
| 🔴 Red | `style="danger"` | Destructive actions (skip, decline, cancel) |
| ⬜ Default | (no style) | Neutral actions |

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

InlineKeyboardButton(text="✅ Accept", callback_data="yes", style="success")
InlineKeyboardButton(text="❌ Decline", callback_data="no",  style="danger")
InlineKeyboardButton(text="ℹ️ Info",    callback_data="i",   style="primary")
```

---

## 📊 Character Pool

The bot ships with **508 anime girl characters** across **86 series**:

| Tier | Count | Spawn weight |
|---|---|---|
| 🌟 Mythic | 14 | 1% |
| 💎 Legendary | 50 | 4% |
| 🔮 Epic | 101 | 12% |
| ⭐ Rare | 127 | 25% |
| 🟢 Uncommon | 144 | 40% |
| ⚪ Common | 72 | 18% |

Add your own via the CSV at `data/waifu_characters.csv` — schema:

```
id,name,anime,role,rarity,rarity_score,popularity_tier,description,aliases,image_url
```

---

## ⚙️ Configuration

All settings live in `.env` (see `.env.example`):

| Key | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | From @BotFather |
| `DATABASE_URL` | — | Postgres DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `USE_WEBHOOK` | `false` | `true` for prod, `false` for dev polling |
| `WEBHOOK_URL` | — | Public HTTPS URL for webhook mode |
| `SPAWN_MSG_INTERVAL` | `100` | Spawn every N group messages |
| `SPAWN_TIME_FLOOR` | `300` | Or every N seconds |
| `SPAWN_CLAIM_WINDOW` | `90` | Seconds before spawn escapes |
| `GUESS_COOLDOWN` | `3` | Per-user /guess cooldown |
| `TRADE_WINDOW` | `60` | Seconds to accept a trade |
| `OWNER_ID` | `0` | Your Telegram user ID |

---

## 🛡️ Anti-Abuse Features

- ⏱️ Per-user / per-command cooldown via Redis (e.g. `/guess` every 3s)
- 👻 Ephemeral Messages for wrong guesses — no group spam, no Telegram flood bans
- 🔐 `SELECT FOR UPDATE` on active spawns — only one user can claim a character
- 🧹 Background cleanup loop expires abandoned spawns every 30s
- 👑 Admin-only `/changetime`

---

## 📜 License

MIT — fork it, ship it, sell it. Just don't blame me if your group gets too addicted.

---

## 🙏 Acknowledgements

- Built on [aiogram](https://github.com/aiogram/aiogram) 3.30
- Character data inspired by community Mudae-style catchers
- Telegram Bot API docs at [core.telegram.org/bots/api](https://core.telegram.org/bots/api)

<div align="center">

⭐ **Star this repo if it helped you!** ⭐

Made with 💜 and way too much caffeine.

</div>

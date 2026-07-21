"""Database schema for WaifuGrabberBot.

Run via `python -m bot.db.init_db` to apply to a fresh Postgres instance.
"""
SCHEMA_SQL = """
-- ============================================================================
-- Characters (spawn pool) — populated from data/waifu_characters.csv
-- ============================================================================
CREATE TABLE IF NOT EXISTS characters (
    id            BIGINT PRIMARY KEY,
    name          TEXT NOT NULL,
    anime         TEXT NOT NULL,
    role          TEXT NOT NULL,
    rarity        TEXT NOT NULL,
    rarity_score  INT  NOT NULL,
    popularity_tier INT NOT NULL,
    description   TEXT NOT NULL,
    aliases       TEXT NOT NULL,
    image_url     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_characters_rarity ON characters (rarity);
CREATE INDEX IF NOT EXISTS idx_characters_anime  ON characters (anime);

-- ============================================================================
-- Groups (per-chat config + activity counter)
-- ============================================================================
CREATE TABLE IF NOT EXISTS groups (
    chat_id          BIGINT PRIMARY KEY,
    title            TEXT NOT NULL DEFAULT '',
    username         TEXT,
    spawn_interval   INT  NOT NULL DEFAULT 100,
    spawn_time_floor INT  NOT NULL DEFAULT 300,
    claim_window     INT  NOT NULL DEFAULT 90,
    msg_counter      INT  NOT NULL DEFAULT 0,
    last_spawn_at    BIGINT NOT NULL DEFAULT 0,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_groups_enabled ON groups (enabled);

-- ============================================================================
-- Users (global identity)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT PRIMARY KEY,
    username       TEXT,
    full_name      TEXT NOT NULL DEFAULT '',
    language_code  TEXT,
    total_claims   INT NOT NULL DEFAULT 0,
    highest_rarity TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Active spawns (one row per "live" character in a chat)
-- ============================================================================
CREATE TABLE IF NOT EXISTS active_spawns (
    chat_id      BIGINT NOT NULL,
    character_id BIGINT NOT NULL REFERENCES characters (id),
    message_id   BIGINT NOT NULL,
    spawned_at   BIGINT NOT NULL,
    expires_at   BIGINT NOT NULL,
    PRIMARY KEY (chat_id)
);
CREATE INDEX IF NOT EXISTS idx_active_spawns_expires ON active_spawns (expires_at);

-- ============================================================================
-- Harem (user × character ownership — per-group)
-- ============================================================================
CREATE TABLE IF NOT EXISTS harem (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users (user_id),
    chat_id      BIGINT NOT NULL,
    character_id BIGINT NOT NULL REFERENCES characters (id),
    is_favorite  BOOLEAN NOT NULL DEFAULT FALSE,
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, chat_id, character_id)
);
CREATE INDEX IF NOT EXISTS idx_harem_user_chat ON harem (user_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_harem_chat      ON harem (chat_id);

-- ============================================================================
-- Trades (audit log of /trade proposals + acceptances)
-- ============================================================================
CREATE TABLE IF NOT EXISTS trades (
    id                BIGSERIAL PRIMARY KEY,
    chat_id           BIGINT NOT NULL,
    from_user_id      BIGINT NOT NULL,
    to_user_id        BIGINT NOT NULL,
    from_character_id BIGINT NOT NULL REFERENCES characters (id),
    to_character_id   BIGINT NOT NULL REFERENCES characters (id),
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ
);

-- ============================================================================
-- Group stats (spawn counter per chat — for /topgroups)
-- ============================================================================
CREATE TABLE IF NOT EXISTS group_stats (
    chat_id       BIGINT PRIMARY KEY REFERENCES groups (chat_id) ON DELETE CASCADE,
    total_spawns  INT NOT NULL DEFAULT 0,
    total_claims  INT NOT NULL DEFAULT 0
);

-- ============================================================================
-- User-group aggregate (for /ctop)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_group_stats (
    user_id      BIGINT NOT NULL,
    chat_id      BIGINT NOT NULL,
    claims       INT NOT NULL DEFAULT 0,
    rarity_score INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, chat_id)
);
"""

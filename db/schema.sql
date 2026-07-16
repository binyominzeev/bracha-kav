-- Bracha Kavana App — Database Schema
-- Designed for SQLite (local dev) but compatible with PostgreSQL.
-- Avoid SQLite-only syntax (e.g., use TEXT for dates instead of DATETIME
-- with SQLite-specific defaults that differ from Postgres behavior).

-- ─── Brachot (individual blessings) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brachot (
    id              TEXT PRIMARY KEY,           -- e.g. "modeh_ani"
    name_hebrew     TEXT NOT NULL,
    name_hungarian  TEXT NOT NULL,
    category        TEXT NOT NULL,              -- e.g. "birkot_hashachar"
    frequency_tier  TEXT NOT NULL DEFAULT 'daily',  -- daily | frequent | occasional
    sefaria_ref     TEXT,                       -- primary Sefaria reference (if any)
    keywords        TEXT,                       -- JSON array stored as text
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─── Cards (kavana cards) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bracha_id       TEXT NOT NULL REFERENCES brachot(id),
    text_content    TEXT NOT NULL,
    source_name     TEXT NOT NULL,              -- e.g. "Tanya, Chapter 41"
    source_ref      TEXT,                       -- Sefaria ref or citation string
    source_url      TEXT,                       -- Sefaria URL if available
    source_license  TEXT,                       -- e.g. "CC BY-NC 4.0" or "public domain"
    mood            TEXT,                       -- gratitude | request | awe | struggle
    depth_level     TEXT,                       -- light | medium | deep
    source_type     TEXT,                       -- chassidic | mussar | modern | personal
    occasion        TEXT,                       -- weekday | shabbat | chag | general
    length_tier     TEXT,                       -- short | medium | long
    confidence      REAL,                       -- 0.0–1.0: AI confidence this card is relevant
    approved        INTEGER NOT NULL DEFAULT 0, -- 0=false, 1=true (SQLite boolean)
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_cards_bracha ON cards(bracha_id);
CREATE INDEX IF NOT EXISTS idx_cards_approved ON cards(approved);
CREATE INDEX IF NOT EXISTS idx_cards_mood ON cards(mood);
CREATE INDEX IF NOT EXISTS idx_cards_source_type ON cards(source_type);
CREATE INDEX IF NOT EXISTS idx_cards_occasion ON cards(occasion);

-- ─── User swipes (defined but empty — not used until recommendation phase) ───
CREATE TABLE IF NOT EXISTS user_swipes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,              -- placeholder, no auth yet
    card_id         INTEGER NOT NULL REFERENCES cards(id),
    direction       TEXT NOT NULL,              -- like | dislike
    swiped_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_swipes_user ON user_swipes(user_id);
CREATE INDEX IF NOT EXISTS idx_swipes_card ON user_swipes(card_id);

-- ─── User preferences (defined but empty — not used until recommendation phase)
CREATE TABLE IF NOT EXISTS user_preferences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    pref_key        TEXT NOT NULL,              -- e.g. "mood", "source_type"
    pref_value      TEXT NOT NULL,              -- e.g. "awe", "chassidic"
    weight          REAL NOT NULL DEFAULT 1.0,  -- learned preference weight
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(user_id, pref_key, pref_value)
);

CREATE INDEX IF NOT EXISTS idx_prefs_user ON user_preferences(user_id);

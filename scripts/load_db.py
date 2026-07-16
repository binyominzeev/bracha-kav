#!/usr/bin/env python3
"""
Load categories and approved cards into the SQLite database.

This script:
  1. Applies db/schema.sql to create / migrate tables (idempotent).
  2. Loads brachot from /data/categories.json.
  3. Loads approved cards from /data/cards/{category}/{bracha_id}.json.
     Pass --all to also load unapproved cards (e.g., for local review).

Usage:
    python scripts/load_db.py
    python scripts/load_db.py --all    # load approved AND unapproved cards
    python scripts/load_db.py --reset  # drop + recreate schema first
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO_ROOT / "db" / "schema.sql"
CATEGORIES_FILE = REPO_ROOT / "data" / "categories.json"
CARDS_DIR = REPO_ROOT / "data" / "cards"
DB_PATH = REPO_ROOT / "db" / "bracha_app.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def apply_schema(conn: sqlite3.Connection, *, reset: bool = False) -> None:
    if reset:
        log.warning("--reset: dropping all tables")
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()

    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    log.info("Schema applied.")


def load_brachot(conn: sqlite3.Connection, categories: list) -> int:
    cur = conn.cursor()
    count = 0
    for cat in categories:
        cat_id = cat["id"]
        for bracha in cat.get("brachot", []):
            refs = bracha.get("sefaria_refs", [])
            keywords = bracha.get("keywords", [])
            cur.execute(
                """
                INSERT INTO brachot
                    (id, name_hebrew, name_hungarian, category,
                     frequency_tier, sefaria_ref, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name_hebrew    = excluded.name_hebrew,
                    name_hungarian = excluded.name_hungarian,
                    category       = excluded.category,
                    frequency_tier = excluded.frequency_tier,
                    sefaria_ref    = excluded.sefaria_ref,
                    keywords       = excluded.keywords
                """,
                (
                    bracha["id"],
                    bracha.get("name_hebrew", ""),
                    bracha.get("name_hungarian", ""),
                    cat_id,
                    bracha.get("frequency_tier", "daily"),
                    refs[0] if refs else None,
                    json.dumps(keywords, ensure_ascii=False),
                ),
            )
            count += 1
    conn.commit()
    return count


def load_cards(conn: sqlite3.Connection, *, load_all: bool = False) -> int:
    cur = conn.cursor()
    total = 0
    if not CARDS_DIR.exists():
        log.info("No cards directory found at %s — skipping card import.", CARDS_DIR)
        return 0

    for card_file in sorted(CARDS_DIR.rglob("*.json")):
        with card_file.open(encoding="utf-8") as fh:
            data = json.load(fh)

        bracha_id = data.get("bracha_id", card_file.stem)
        cards = data.get("cards", [])
        for card in cards:
            approved = bool(card.get("approved", False))
            if not load_all and not approved:
                continue
            cur.execute(
                """
                INSERT INTO cards
                    (bracha_id, text_content, source_name, source_ref,
                     source_url, source_license, mood, depth_level,
                     source_type, occasion, length_tier, confidence, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bracha_id,
                    card.get("text_content", ""),
                    card.get("source_name", ""),
                    card.get("source_ref", ""),
                    card.get("source_url", ""),
                    card.get("source_license", ""),
                    card.get("mood", ""),
                    card.get("depth_level", ""),
                    card.get("source_type", ""),
                    card.get("occasion", ""),
                    card.get("length_tier", ""),
                    card.get("confidence"),
                    1 if approved else 0,
                ),
            )
            total += 1

    conn.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load categories and cards into the SQLite database."
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Load both approved and unapproved cards.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop and recreate all tables before loading.",
    )
    args = parser.parse_args()

    if not SCHEMA_FILE.exists():
        log.error("Schema file not found: %s", SCHEMA_FILE)
        sys.exit(1)
    if not CATEGORIES_FILE.exists():
        log.error("categories.json not found: %s", CATEGORIES_FILE)
        sys.exit(1)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        apply_schema(conn, reset=args.reset)

        with CATEGORIES_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        n_brachot = load_brachot(conn, data.get("categories", []))
        log.info("Loaded %d brachot.", n_brachot)

        n_cards = load_cards(conn, load_all=args.all)
        log.info("Loaded %d cards (load_all=%s).", n_cards, args.all)

        log.info("Database ready at %s", DB_PATH)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

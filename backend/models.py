"""
Database access layer for the Bracha Kavana app.

Uses raw sqlite3 for portability — no ORM dependency.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "bracha_app.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── Brachot ──────────────────────────────────────────────────────────────────

def get_all_brachot() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM brachot ORDER BY category, id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_brachot_by_category(category: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM brachot WHERE category = ? ORDER BY id",
            (category,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_bracha(bracha_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM brachot WHERE id = ?", (bracha_id,)
        ).fetchone()
    return dict(row) if row else None


# ─── Cards ────────────────────────────────────────────────────────────────────

def get_cards_for_bracha(
    bracha_id: str,
    *,
    approved_only: bool = False,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM cards WHERE bracha_id = ?"
    params: list[Any] = [bracha_id]
    if approved_only:
        sql += " AND approved = 1"
    sql += " ORDER BY confidence DESC, id"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_all_cards(
    *,
    approved_only: bool = False,
    mood: str | None = None,
    source_type: str | None = None,
    occasion: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if approved_only:
        conditions.append("c.approved = 1")
    if mood:
        conditions.append("c.mood = ?")
        params.append(mood)
    if source_type:
        conditions.append("c.source_type = ?")
        params.append(source_type)
    if occasion:
        conditions.append("c.occasion = ?")
        params.append(occasion)
    if category:
        conditions.append("b.category = ?")
        params.append(category)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT c.*, b.category, b.name_hebrew, b.name_hungarian
        FROM cards c
        JOIN brachot b ON c.bracha_id = b.id
        {where}
        ORDER BY b.category, c.bracha_id, c.confidence DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_card(card_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


def set_card_approved(card_id: int, approved: bool) -> bool:
    """Toggle approval status. Returns True if a row was updated."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE cards SET approved = ? WHERE id = ?",
            (1 if approved else 0, card_id),
        )
        conn.commit()
    return cur.rowcount > 0


# ─── Categories list (distinct values from brachot) ───────────────────────────

def get_categories() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM brachot ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]

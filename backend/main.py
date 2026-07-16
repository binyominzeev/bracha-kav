"""
FastAPI backend for the Bracha Kavana App.

Serves card browsing endpoints consumed by the frontend.

Run:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import backend.models as db

app = FastAPI(
    title="Bracha Kavana API",
    description="Browse and approve kavana cards for Jewish prayer.",
    version="0.1.0",
)

# Allow the static frontend to call the API from any origin during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
)

# ─── Serve static frontend ────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if (FRONTEND_DIR / "index.html").exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))


# ─── Categories ───────────────────────────────────────────────────────────────

@app.get("/api/categories", tags=["categories"])
async def list_categories() -> list[str]:
    """Return a list of all bracha category IDs."""
    return db.get_categories()


# ─── Brachot ──────────────────────────────────────────────────────────────────

@app.get("/api/brachot", tags=["brachot"])
async def list_brachot(
    category: Annotated[str | None, Query(description="Filter by category ID")] = None,
) -> list[dict[str, Any]]:
    """Return all brachot, optionally filtered by category."""
    if category:
        return db.get_brachot_by_category(category)
    return db.get_all_brachot()


@app.get("/api/brachot/{bracha_id}", tags=["brachot"])
async def get_bracha(bracha_id: str) -> dict[str, Any]:
    bracha = db.get_bracha(bracha_id)
    if not bracha:
        raise HTTPException(status_code=404, detail=f"Bracha {bracha_id!r} not found.")
    return bracha


# ─── Cards ────────────────────────────────────────────────────────────────────

@app.get("/api/cards", tags=["cards"])
async def list_cards(
    bracha_id: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    mood: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    occasion: Annotated[str | None, Query()] = None,
    approved_only: Annotated[bool, Query()] = False,
) -> list[dict[str, Any]]:
    """Return cards with optional filtering."""
    if bracha_id:
        return db.get_cards_for_bracha(bracha_id, approved_only=approved_only)
    return db.get_all_cards(
        approved_only=approved_only,
        mood=mood,
        source_type=source_type,
        occasion=occasion,
        category=category,
    )


@app.get("/api/cards/{card_id}", tags=["cards"])
async def get_card(card_id: int) -> dict[str, Any]:
    card = db.get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found.")
    return card


@app.patch("/api/cards/{card_id}/approve", tags=["cards"])
async def approve_card(card_id: int) -> dict[str, Any]:
    """Mark a card as approved."""
    if not db.set_card_approved(card_id, approved=True):
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found.")
    return {"card_id": card_id, "approved": True}


@app.patch("/api/cards/{card_id}/reject", tags=["cards"])
async def reject_card(card_id: int) -> dict[str, Any]:
    """Mark a card as rejected (unapproved)."""
    if not db.set_card_approved(card_id, approved=False):
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found.")
    return {"card_id": card_id, "approved": False}


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

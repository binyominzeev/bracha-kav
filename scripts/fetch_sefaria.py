#!/usr/bin/env python3
"""
Stage 1 — Fetch raw texts from the Sefaria API.

For each bracha defined in /data/categories.json this script:
  1. Calls the Sefaria /api/related/{ref} endpoint (related texts).
  2. Falls back to / supplements with /api/search-wrapper (keyword search).
  3. Saves the combined raw JSON to /data/raw/{category}/{bracha_id}.json.
  4. Logs result counts per bracha to stdout.
  5. Respects Sefaria rate limits (configurable delay, exponential-backoff retry).
  6. Is idempotent — skips already-fetched files unless --force is passed.

Usage:
    python scripts/fetch_sefaria.py
    python scripts/fetch_sefaria.py --force          # re-fetch everything
    python scripts/fetch_sefaria.py --category amidah  # single category
    python scripts/fetch_sefaria.py --bracha shema     # single bracha id
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
CATEGORIES_FILE = REPO_ROOT / "data" / "categories.json"
RAW_DIR = REPO_ROOT / "data" / "raw"

# ─── Sefaria API base URLs ────────────────────────────────────────────────────
SEFARIA_BASE = "https://www.sefaria.org/api"

# Delay between Sefaria API calls (seconds). Sefaria asks for courtesy delays.
REQUEST_DELAY = float(os.getenv("SEFARIA_DELAY", "1.0"))

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── HTTP session with retry logic ────────────────────────────────────────────

def build_session() -> requests.Session:
    """Build a requests Session with exponential-backoff retry."""
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2.0,          # delays: 2s, 4s, 8s, 16s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "bracha-kav-fetcher/1.0 (educational project)",
    })
    return session


SESSION = build_session()


# ─── Sefaria API helpers ───────────────────────────────────────────────────────

def get_related(ref: str) -> dict[str, Any]:
    """
    Fetch related texts for a Sefaria reference via /api/related/{ref}.
    Returns the raw JSON dict (may be empty on 404).
    """
    url = f"{SEFARIA_BASE}/related/{requests.utils.quote(ref, safe='')}"
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 404:
            log.debug("related 404 for ref=%r", ref)
            return {}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("related request failed for ref=%r: %s", ref, exc)
        return {}
    finally:
        time.sleep(REQUEST_DELAY)


def get_text(ref: str) -> dict[str, Any]:
    """
    Fetch the actual text of a Sefaria reference via /api/texts/{ref}.
    Returns the raw JSON dict (may be empty on 404).
    """
    url = f"{SEFARIA_BASE}/texts/{requests.utils.quote(ref, safe='')}"
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 404:
            log.debug("texts 404 for ref=%r", ref)
            return {}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("texts request failed for ref=%r: %s", ref, exc)
        return {}
    finally:
        time.sleep(REQUEST_DELAY)


def search_keyword(keyword: str, size: int = 10) -> dict[str, Any]:
    """
    Full-text search on Sefaria using /api/search-wrapper.
    Returns the raw search JSON or an empty dict on error.
    """
    url = f"{SEFARIA_BASE}/search-wrapper"
    payload = {
        "query": keyword,
        "type": "text",
        "field": "naive_lemmatizer",
        "slop": 1,
        "sort_type": "_score",
        "sort_direction": "desc",
        "pgsize": size,
        "start": 0,
    }
    try:
        resp = SESSION.post(url, json=payload, timeout=25)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("search failed for keyword=%r: %s", keyword, exc)
        return {}
    finally:
        time.sleep(REQUEST_DELAY)


# ─── Count helpers ─────────────────────────────────────────────────────────────

def count_related_results(data: dict[str, Any]) -> int:
    """Return the total number of related-text entries found."""
    total = 0
    for key in ("links", "notes", "webpages", "topics"):
        val = data.get(key)
        if isinstance(val, list):
            total += len(val)
    return total


def count_search_hits(data: dict[str, Any]) -> int:
    """Return the number of search hits from a search-wrapper response."""
    try:
        return data.get("hits", {}).get("total", {}).get("value", 0)
    except (AttributeError, TypeError):
        return 0


# ─── Core fetch logic ──────────────────────────────────────────────────────────

def fetch_bracha(
    category_id: str,
    bracha: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Fetch all available Sefaria data for one bracha and return a combined dict.

    Returns a result summary dict with keys:
        bracha_id, related_count, text_count, search_count, skipped, path
    """
    bracha_id: str = bracha["id"]
    out_dir = RAW_DIR / category_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{bracha_id}.json"

    if out_path.exists() and not force:
        log.info("  [SKIP] %s/%s — already fetched", category_id, bracha_id)
        # Load existing to report counts
        with out_path.open(encoding="utf-8") as fh:
            existing = json.load(fh)
        return {
            "bracha_id": bracha_id,
            "related_count": sum(
                len(v) for v in existing.get("related", {}).values() if isinstance(v, list)
            ),
            "text_count": len(existing.get("texts", [])),
            "search_count": sum(
                r.get("hits_total", 0) for r in existing.get("search_results", [])
            ),
            "skipped": True,
            "path": str(out_path),
        }

    refs: list[str] = bracha.get("sefaria_refs", [])
    keywords: list[str] = bracha.get("keywords", [])

    combined: dict[str, Any] = {
        "bracha_id": bracha_id,
        "category_id": category_id,
        "name_hebrew": bracha.get("name_hebrew", ""),
        "name_hungarian": bracha.get("name_hungarian", ""),
        "sefaria_refs": refs,
        "keywords": keywords,
        "related": {},
        "texts": [],
        "search_results": [],
    }

    # 1. Fetch related texts for each explicit Sefaria ref
    for ref in refs:
        log.info("  [related] %s — ref: %s", bracha_id, ref)
        related_data = get_related(ref)
        if related_data:
            combined["related"][ref] = related_data

        # Also fetch the actual text for the ref
        log.info("  [text]    %s — ref: %s", bracha_id, ref)
        text_data = get_text(ref)
        if text_data:
            combined["texts"].append({"ref": ref, "data": text_data})

    # 2. Keyword search as fallback / supplement
    # Use the first 3 keywords to avoid excessive API calls
    search_keywords = keywords[:3] if keywords else []
    for kw in search_keywords:
        log.info("  [search]  %s — keyword: %r", bracha_id, kw)
        search_data = search_keyword(kw, size=8)
        if search_data:
            hit_count = count_search_hits(search_data)
            combined["search_results"].append({
                "keyword": kw,
                "hits_total": hit_count,
                "data": search_data,
            })

    # 3. Compute richness counts for logging
    related_count = sum(
        count_related_results(v)
        for v in combined["related"].values()
        if isinstance(v, dict)
    )
    text_count = len(combined["texts"])
    search_count = sum(r.get("hits_total", 0) for r in combined["search_results"])

    # 4. Save
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(combined, fh, ensure_ascii=False, indent=2)
    log.info(
        "  [SAVED] %s/%s → related=%d, texts=%d, search_hits=%d",
        category_id, bracha_id, related_count, text_count, search_count,
    )

    return {
        "bracha_id": bracha_id,
        "related_count": related_count,
        "text_count": text_count,
        "search_count": search_count,
        "skipped": False,
        "path": str(out_path),
    }


# ─── Summary table ─────────────────────────────────────────────────────────────

def print_summary(results: list[dict[str, Any]]) -> None:
    """Print a richness-signal table to stdout."""
    print("\n" + "=" * 72)
    print(f"{'bracha_id':<32} {'related':>8} {'texts':>6} {'searches':>9} {'status':>7}")
    print("=" * 72)
    for r in results:
        status = "SKIP" if r["skipped"] else "NEW"
        print(
            f"{r['bracha_id']:<32} "
            f"{r['related_count']:>8} "
            f"{r['text_count']:>6} "
            f"{r['search_count']:>9} "
            f"{status:>7}"
        )
    print("=" * 72)
    total_rel = sum(r["related_count"] for r in results)
    total_txt = sum(r["text_count"] for r in results)
    total_srch = sum(r["search_count"] for r in results)
    print(
        f"{'TOTAL':<32} {total_rel:>8} {total_txt:>6} {total_srch:>9}"
    )
    print()

    # Highlight sparse brachot that may need human-written cards
    sparse = [
        r["bracha_id"]
        for r in results
        if (r["related_count"] + r["text_count"]) == 0 and not r["skipped"]
    ]
    if sparse:
        print(
            "⚠  Sparse (no related/text results — may need human-sourced cards):\n   "
            + ", ".join(sparse)
        )
        print()


# ─── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 1: Fetch raw Sefaria data for all brachot."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch and overwrite already-fetched files.",
    )
    parser.add_argument(
        "--category",
        metavar="CATEGORY_ID",
        help="Only fetch brachot from this category (e.g. amidah).",
    )
    parser.add_argument(
        "--bracha",
        metavar="BRACHA_ID",
        help="Only fetch this single bracha (e.g. shema).",
    )
    args = parser.parse_args()

    if not CATEGORIES_FILE.exists():
        log.error("categories.json not found at %s", CATEGORIES_FILE)
        sys.exit(1)

    with CATEGORIES_FILE.open(encoding="utf-8") as fh:
        data = json.load(fh)

    categories: list[dict[str, Any]] = data.get("categories", [])
    all_results: list[dict[str, Any]] = []

    for cat in categories:
        cat_id: str = cat["id"]

        if args.category and cat_id != args.category:
            continue

        log.info("─── Category: %s ───", cat_id)

        for bracha in cat.get("brachot", []):
            if args.bracha and bracha["id"] != args.bracha:
                continue

            result = fetch_bracha(cat_id, bracha, force=args.force)
            result["category_id"] = cat_id
            all_results.append(result)

    if not all_results:
        log.warning("No brachot matched the given filters — nothing fetched.")
        sys.exit(0)

    print_summary(all_results)
    log.info("Done. Raw files saved under %s", RAW_DIR)


if __name__ == "__main__":
    main()

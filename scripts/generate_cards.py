#!/usr/bin/env python3
"""
Stage 2 — AI card generation (skeleton).

Reads raw JSON files from /data/raw, sends source material to the
configured AI provider, and saves structured kavana cards to /data/cards.

IMPORTANT: Do NOT run this script until Stage 1 output has been reviewed
and you are ready to incur AI API costs. Use scripts/estimate_cost.py first.

Usage:
    python scripts/generate_cards.py
    python scripts/generate_cards.py --category amidah
    python scripts/generate_cards.py --bracha shema
    python scripts/generate_cards.py --force   # regenerate existing cards
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
CARDS_DIR = REPO_ROOT / "data" / "cards"
CATEGORIES_FILE = REPO_ROOT / "data" / "categories.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── JSON Schema for the AI response ──────────────────────────────────────────
CARD_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["bracha_id", "richness", "cards"],
    "properties": {
        "bracha_id": {"type": "string"},
        "richness": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "0–1 score: how much relevant source material existed",
        },
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text_content", "source_name", "source_ref", "mood",
                             "depth_level", "source_type", "occasion", "confidence"],
                "properties": {
                    "text_content": {"type": "string"},
                    "source_name":  {"type": "string"},
                    "source_ref":   {"type": "string"},
                    "source_url":   {"type": "string"},
                    "mood": {
                        "type": "string",
                        "enum": ["gratitude", "request", "awe", "struggle"],
                    },
                    "depth_level": {
                        "type": "string",
                        "enum": ["light", "medium", "deep"],
                    },
                    "source_type": {
                        "type": "string",
                        "enum": ["chassidic", "mussar", "modern", "personal"],
                    },
                    "occasion": {
                        "type": "string",
                        "enum": ["weekday", "shabbat", "chag", "general"],
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        },
    },
}

SYSTEM_PROMPT = """\
You are a scholarly assistant helping to create kavana (intention/reflection) \
cards for Jewish prayer. You extract relevant passages from authoritative \
Jewish sources and condense them into short, meaningful cards.

Rules:
- Extract ONLY passages genuinely relevant to the specific bracha's theme.
- Condense each passage to 2-5 sentences.
- Use the source's ORIGINAL LANGUAGE when quoting directly (accuracy matters).
- Use a faithful Hungarian paraphrase when the original is a paraphrase/summary.
- ALWAYS include the exact source reference (book, author, chapter/verse).
- If nothing is genuinely relevant, return an empty cards list — do NOT \
  force low-quality cards.
- Output valid JSON only, matching the provided schema exactly.
- Never invent liturgical text or halachic rulings not present in the sources.
"""


def build_prompt(raw_data: dict[str, Any]) -> str:
    """Build the user prompt from the raw Sefaria data dict."""
    bracha_id = raw_data.get("bracha_id", "unknown")
    name_heb = raw_data.get("name_hebrew", "")
    name_hun = raw_data.get("name_hungarian", "")
    keywords = ", ".join(raw_data.get("keywords", []))

    # Summarise available source material (truncated to avoid huge prompts)
    source_summary_parts: list[str] = []

    for ref, related in raw_data.get("related", {}).items():
        links = related.get("links", [])[:5]
        if links:
            source_summary_parts.append(
                f"Related texts for {ref}:\n"
                + "\n".join(
                    f"  - {lnk.get('ref', '?')}: {lnk.get('he', '')[:120]}"
                    for lnk in links
                )
            )

    for text_entry in raw_data.get("texts", [])[:3]:
        ref = text_entry.get("ref", "?")
        data = text_entry.get("data", {})
        he = data.get("he", "")
        en = data.get("text", "")
        # Flatten nested lists
        if isinstance(he, list):
            he = " ".join(str(x) for x in he if x)[:400]
        if isinstance(en, list):
            en = " ".join(str(x) for x in en if x)[:400]
        if he or en:
            source_summary_parts.append(
                f"Text {ref}:\n  Hebrew: {he[:300]}\n  English: {en[:300]}"
            )

    for sr in raw_data.get("search_results", [])[:2]:
        kw = sr.get("keyword", "")
        hits = sr.get("data", {}).get("hits", {}).get("hits", [])[:3]
        if hits:
            source_summary_parts.append(
                f"Search results for '{kw}':\n"
                + "\n".join(
                    "  - {ref}: {content}".format(
                        ref=h.get("_source", {}).get("ref", "?"),
                        content=h.get("_source", {}).get("content", "")[:150],
                    )
                    for h in hits
                )
            )

    source_block = "\n\n".join(source_summary_parts) if source_summary_parts else "(no sources found)"

    return f"""\
Bracha: {bracha_id}
Hebrew name: {name_heb}
Hungarian name: {name_hun}
Themes/keywords: {keywords}

Source material from Sefaria:
{source_block}

Please generate kavana cards from this material.
Return JSON matching this schema:
{json.dumps(CARD_RESPONSE_SCHEMA, indent=2)}
"""


def generate_cards_for_bracha(
    category_id: str,
    bracha_id: str,
    *,
    provider: Any,
    force: bool = False,
) -> dict[str, Any] | None:
    """Generate cards for one bracha. Returns summary or None on skip."""
    raw_path = RAW_DIR / category_id / f"{bracha_id}.json"
    if not raw_path.exists():
        log.warning("Raw file not found: %s — skipping", raw_path)
        return None

    out_dir = CARDS_DIR / category_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{bracha_id}.json"

    if out_path.exists() and not force:
        log.info("  [SKIP] %s/%s — cards already generated", category_id, bracha_id)
        with out_path.open(encoding="utf-8") as fh:
            existing = json.load(fh)
        cards = existing.get("cards", [])
        return {
            "bracha_id": bracha_id,
            "cards_generated": len(cards),
            "avg_confidence": (
                sum(c.get("confidence", 0) for c in cards) / len(cards)
                if cards else 0.0
            ),
            "richness": existing.get("richness", 0.0),
            "skipped": True,
        }

    with raw_path.open(encoding="utf-8") as fh:
        raw_data = json.load(fh)

    prompt = build_prompt(raw_data)

    log.info("  [AI]  %s/%s — calling %s/%s", category_id, bracha_id,
             provider.provider_name, provider.model)
    result = provider.generate_structured(
        prompt,
        CARD_RESPONSE_SCHEMA,
        system_prompt=SYSTEM_PROMPT,
    )

    # Annotate cards with default approved=False and source metadata
    for card in result.get("cards", []):
        card.setdefault("approved", False)

    result["bracha_id"] = bracha_id
    result["category_id"] = category_id

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    cards = result.get("cards", [])
    avg_conf = (
        sum(c.get("confidence", 0) for c in cards) / len(cards)
        if cards else 0.0
    )
    log.info(
        "  [SAVED] %s/%s → %d cards, avg_confidence=%.2f",
        category_id, bracha_id, len(cards), avg_conf,
    )
    return {
        "bracha_id": bracha_id,
        "cards_generated": len(cards),
        "avg_confidence": avg_conf,
        "richness": result.get("richness", 0.0),
        "skipped": False,
    }


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 68)
    print(f"{'bracha_id':<30} {'cards':>6} {'avg_conf':>9} {'richness':>9} {'status':>7}")
    print("=" * 68)
    for r in results:
        status = "SKIP" if r["skipped"] else "NEW"
        print(
            f"{r['bracha_id']:<30} "
            f"{r['cards_generated']:>6} "
            f"{r['avg_confidence']:>9.2f} "
            f"{r['richness']:>9.2f} "
            f"{status:>7}"
        )
    print("=" * 68)
    total_cards = sum(r["cards_generated"] for r in results)
    low_richness = [r["bracha_id"] for r in results if r["richness"] < 0.3]
    print(f"Total cards generated: {total_cards}")
    if low_richness:
        print(
            "\n⚠  Low richness — consider adding human-sourced content for:\n   "
            + ", ".join(low_richness)
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 2: Generate kavana cards using the configured AI provider."
    )
    parser.add_argument("--force", action="store_true", help="Regenerate existing cards.")
    parser.add_argument("--category", metavar="CATEGORY_ID")
    parser.add_argument("--bracha", metavar="BRACHA_ID")
    args = parser.parse_args()

    if not CATEGORIES_FILE.exists():
        log.error("categories.json not found at %s", CATEGORIES_FILE)
        sys.exit(1)

    # Lazy import so missing API keys don't block --help
    from ai_providers import get_provider  # noqa: PLC0415
    provider = get_provider()
    log.info("Using provider=%s model=%s", provider.provider_name, provider.model)

    with CATEGORIES_FILE.open(encoding="utf-8") as fh:
        data = json.load(fh)

    all_results: list[dict[str, Any]] = []
    for cat in data.get("categories", []):
        cat_id: str = cat["id"]
        if args.category and cat_id != args.category:
            continue
        log.info("─── Category: %s ───", cat_id)
        for bracha in cat.get("brachot", []):
            if args.bracha and bracha["id"] != args.bracha:
                continue
            result = generate_cards_for_bracha(
                cat_id, bracha["id"], provider=provider, force=args.force
            )
            if result is not None:
                result.setdefault("category_id", cat_id)
                all_results.append(result)

    if not all_results:
        log.warning("No brachot matched filters — nothing generated.")
        sys.exit(0)

    print_summary(all_results)
    log.info("Done. Card files saved under %s", CARDS_DIR)


if __name__ == "__main__":
    main()

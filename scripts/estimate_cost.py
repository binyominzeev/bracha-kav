#!/usr/bin/env python3
"""
Stage 3 — Token/cost estimator.

Estimates the AI API cost of running Stage 2 (generate_cards.py) across
all raw Sefaria data in /data/raw BEFORE you actually run it.

Usage:
    python scripts/estimate_cost.py
    python scripts/estimate_cost.py --sample          # 3 brachot per category
    python scripts/estimate_cost.py --sample 5        # 5 brachot per category
    python scripts/estimate_cost.py --category amidah

IMPORTANT: The pricing table below is manually maintained.
           Verify current prices at each provider's pricing page before
           making financial decisions — pricing changes frequently!
           Last verified: see PRICING_LAST_VERIFIED below.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# ─── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "filtered"  # raw Sefaria JSON (Stage 1)
CATEGORIES_FILE = REPO_ROOT / "data" / "categories.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Pricing table ────────────────────────────────────────────────────────────
# !! MANUALLY VERIFY before use — prices change without notice !!
# Prices are USD per 1 million tokens.
PRICING_LAST_VERIFIED = "2025-01"   # Update this when you re-verify

PRICING: dict[str, dict[str, dict[str, float]]] = {
    # provider → model → {input: $/Mtok, output: $/Mtok}
    "openai": {
        "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
        "gpt-4o":           {"input": 2.50,  "output": 10.00},
        "gpt-4-turbo":      {"input": 10.00, "output": 30.00},
    },
    "anthropic": {
        "claude-haiku-3-5": {"input": 0.80,  "output": 4.00},
        "claude-3-haiku":   {"input": 0.25,  "output": 1.25},
        "claude-sonnet-3-5":{"input": 3.00,  "output": 15.00},
    },
    "gemini": {
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro":   {"input": 3.50,  "output": 10.50},
    },
}

# Expected output:input token ratio for Stage 2 prompts (rough heuristic).
# Cards are short; prompts are long. 1:4 is a conservative estimate.
OUTPUT_INPUT_RATIO = 0.25


def char_to_tokens(char_count: int) -> int:
    """Rough token estimate: ~4 chars per token (multilingual, conservative)."""
    return max(1, char_count // 4)


def count_tokens_in_file(path: Path) -> int:
    """Estimate token count of a raw JSON file."""
    try:
        return char_to_tokens(path.stat().st_size)
    except OSError:
        return 0


def lookup_pricing(provider: str, model: str) -> dict[str, float] | None:
    """Return {input, output} pricing per Mtok, or None if unknown."""
    prov_prices = PRICING.get(provider.lower())
    if not prov_prices:
        return None
    # Exact match first, then prefix match
    if model in prov_prices:
        return prov_prices[model]
    for key, prices in prov_prices.items():
        if model.startswith(key) or key.startswith(model):
            return prices
    return None


def estimate_cost(input_tokens: int, pricing: dict[str, float]) -> dict[str, float]:
    """Return {input_cost, output_cost, total_cost} in USD."""
    output_tokens = int(input_tokens * OUTPUT_INPUT_RATIO)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }


def collect_bracha_token_counts(
    categories: list[dict[str, Any]],
    *,
    category_filter: str | None,
    sample: int | None,
) -> list[dict[str, Any]]:
    """Walk /data/raw and return per-bracha token counts."""
    rows: list[dict[str, Any]] = []
    for cat in categories:
        cat_id: str = cat["id"]
        if category_filter and cat_id != category_filter:
            continue

        brachot = cat.get("brachot", [])
        if sample:
            brachot = brachot[:sample]

        for bracha in brachot:
            bracha_id: str = bracha["id"]
            raw_path = RAW_DIR / cat_id / f"{bracha_id}.json"
            tokens = count_tokens_in_file(raw_path) if raw_path.exists() else 0
            rows.append({
                "category_id": cat_id,
                "bracha_id": bracha_id,
                "tokens": tokens,
                "file_exists": raw_path.exists(),
            })

    return rows


def print_breakdown(
    rows: list[dict[str, Any]],
    pricing: dict[str, float] | None,
    *,
    provider: str,
    model: str,
    is_sample: bool,
    total_brachot: int,
) -> None:
    print(f"\n{'=' * 70}")
    print(f"Cost estimate — provider={provider!r}  model={model!r}")
    print(f"Pricing last verified: {PRICING_LAST_VERIFIED}  ← VERIFY BEFORE USE")
    if is_sample:
        sampled = len(rows)
        print(
            f"SAMPLE mode: estimated from {sampled} brachot, "
            f"extrapolated to {total_brachot} total"
        )
    print(f"{'=' * 70}")
    print(f"{'category':<26} {'bracha':<28} {'tokens':>8} {'cost_usd':>10}")
    print("-" * 70)

    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        cat = row["category_id"]
        if cat not in by_category:
            by_category[cat] = {"tokens": 0, "cost": 0.0, "brachot": 0, "missing": 0}
        by_category[cat]["brachot"] += 1
        by_category[cat]["tokens"] += row["tokens"]
        if not row["file_exists"]:
            by_category[cat]["missing"] += 1
        cost = estimate_cost(row["tokens"], pricing)["total_cost"] if pricing else 0.0
        by_category[cat]["cost"] += cost
        missing_marker = " (file missing!)" if not row["file_exists"] else ""
        cost_str = f"${cost:.4f}" if pricing else "N/A"
        print(
            f"{cat:<26} {row['bracha_id']:<28} "
            f"{row['tokens']:>8,} {cost_str:>10}{missing_marker}"
        )

    print("-" * 70)
    grand_tokens = sum(r["tokens"] for r in rows)
    grand_cost = (
        estimate_cost(grand_tokens, pricing)["total_cost"] if pricing else 0.0
    )

    if is_sample and rows:
        scale = total_brachot / len(rows)
        grand_tokens_extrap = int(grand_tokens * scale)
        grand_cost_extrap = estimate_cost(grand_tokens_extrap, pricing)["total_cost"] if pricing else 0.0
    else:
        grand_tokens_extrap = grand_tokens
        grand_cost_extrap = grand_cost

    print(f"\nSampled tokens:  {grand_tokens:>12,}")
    if is_sample and len(rows) > 0:
        print(f"Extrapolated:    {grand_tokens_extrap:>12,}  (×{total_brachot / len(rows):.1f})")
    print(f"\nEstimated cost:  ${grand_cost_extrap:.4f}")
    if pricing:
        detail = estimate_cost(grand_tokens_extrap, pricing)
        print(
            f"  Input  {detail['input_tokens']:>10,} tok  → ${detail['input_cost']:.4f}\n"
            f"  Output {detail['output_tokens']:>10,} tok  → ${detail['output_cost']:.4f}\n"
            f"  (assumes output≈{OUTPUT_INPUT_RATIO:.0%} of input tokens)"
        )
    else:
        print(f"  (pricing not found for {provider}/{model} — add to PRICING dict)")
    print()

    print("Category breakdown:")
    for cat_id, stats in by_category.items():
        cost_str = f"${stats['cost']:.4f}" if pricing else "N/A"
        warn = f" [{stats['missing']} files missing]" if stats["missing"] else ""
        print(
            f"  {cat_id:<28} {stats['brachot']:>3} brachot  "
            f"{stats['tokens']:>8,} tok  {cost_str}{warn}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 3: Estimate AI cost before running generate_cards.py."
    )
    parser.add_argument(
        "--sample", nargs="?", const=3, type=int, metavar="N",
        help="Estimate from N brachot per category and extrapolate (default N=3).",
    )
    parser.add_argument("--category", metavar="CATEGORY_ID")
    args = parser.parse_args()

    provider = os.getenv("PROVIDER", "openai").lower()
    model = os.getenv("MODEL", "gpt-4o-mini")
    pricing = lookup_pricing(provider, model)

    if not CATEGORIES_FILE.exists():
        log.error("categories.json not found at %s", CATEGORIES_FILE)
        sys.exit(1)

    with CATEGORIES_FILE.open(encoding="utf-8") as fh:
        data = json.load(fh)

    categories: list[dict[str, Any]] = data.get("categories", [])

    # Total brachot count (for extrapolation)
    total_brachot = sum(
        len(cat.get("brachot", []))
        for cat in categories
        if not args.category or cat["id"] == args.category
    )

    rows = collect_bracha_token_counts(
        categories,
        category_filter=args.category,
        sample=args.sample,
    )

    if not rows:
        log.warning("No data found. Run fetch_sefaria.py first.")
        sys.exit(0)

    print_breakdown(
        rows,
        pricing,
        provider=provider,
        model=model,
        is_sample=bool(args.sample),
        total_brachot=total_brachot,
    )


if __name__ == "__main__":
    main()

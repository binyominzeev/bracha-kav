"""
Stage 1.5: Pre-filter raw Sefaria JSON before sending to the AI card generator.

Purpose
-------
Raw fetch_sefaria.py output is large (often 1-1.5MB per bracha) but most of
that size is bibliographic metadata or user-sheet metadata with NO usable
prose text. Sending it as-is to an AI API wastes tokens on noise the model
can't use anyway.

This script produces a much smaller "candidates" JSON per bracha that only
contains blocks with actual extractable text, ranked so the highest-value
material comes first. It does NOT call any AI API - it's pure Python,
zero cost, and safe to re-run as often as you like while you tune it.

Usage:
    python filter_raw.py --input data/raw --output data/filtered
    python filter_raw.py --input data/raw --output data/filtered --bracha avot
"""

import argparse
import json
import re
from pathlib import Path

# Categories most likely to contain reflective / kavana-relevant content,
# vs. technical/legal categories that rarely do. Tune this list as you
# review results - it directly controls what gets prioritized for a
# follow-up full-text fetch.
HIGH_VALUE_CATEGORIES = {
    "Chasidut": 3,
    "Musar": 3,
    "Jewish Thought": 3,
    "Midrash": 2,
    "Kabbalah": 2,
    "Essay": 2,
    "Commentary": 1,
    "Quoting Commentary": 1,
    "Tanakh": 1,
}
LOW_VALUE_CATEGORIES = {"Halakhah", "Responsa", "Tosefta", "Reference", "Talmud", "Mishnah"}

# How many top-ranked "links" (which have no text yet, only a ref) to keep
# as candidates for a follow-up /api/texts/{ref} call.
MAX_LINK_CANDIDATES = 15

HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove Sefaria's inline HTML formatting tags (<b>, <i>, <sup>, etc.)."""
    return HTML_TAG_RE.sub("", text).strip()


def score_link(link: dict) -> int:
    cat = link.get("category", "")
    if cat in LOW_VALUE_CATEGORIES:
        return 0
    return HIGH_VALUE_CATEGORIES.get(cat, 1)


def filter_links(links: list) -> list:
    """Links have no text content, only references. Rank them so a later
    'fetch full text for top candidates' step knows where to spend its
    API budget, instead of blindly fetching all 500+."""
    ranked = sorted(links, key=score_link, reverse=True)
    seen_refs = set()
    candidates = []
    for link in ranked:
        if score_link(link) == 0:
            continue
        ref = link.get("ref")
        # dedupe by collective title + ref (Sefaria often repeats the same
        # source at multiple anchor points within a passage)
        key = (link.get("collectiveTitle", {}).get("en"), ref)
        if key in seen_refs:
            continue
        seen_refs.add(key)
        candidates.append({
            "ref": ref,
            "category": link.get("category"),
            "title_en": link.get("collectiveTitle", {}).get("en"),
            "title_he": link.get("collectiveTitle", {}).get("he"),
            "comp_date": link.get("compDate"),
            "has_english": link.get("sourceHasEn", False),
        })
        if len(candidates) >= MAX_LINK_CANDIDATES:
            break
    return candidates


def filter_topics(topics: list) -> list:
    """Topics usually already contain curated title+description prose -
    this is the highest text-per-byte content in the raw file. Keep all,
    but strip fields we don't need (order/pagerank/scoring metadata)."""
    result = []
    for t in topics:
        desc = t.get("descriptions", {}).get("en", {})
        if not desc.get("title") and not desc.get("prompt"):
            continue
        result.append({
            "title": desc.get("title"),
            "text": desc.get("prompt"),
            "source": t.get("dataSource", {}).get("en"),
        })
    return result


def filter_texts(texts: list) -> list:
    """Primary source text. Strip HTML formatting tags, keep plain prose."""
    result = []
    for t in texts:
        data = t.get("data", {})
        raw_paragraphs = data.get("text", [])
        clean = [strip_html(p) for p in raw_paragraphs if p and strip_html(p)]
        if not clean:
            continue
        result.append({
            "ref": data.get("ref"),
            "he_ref": data.get("heRef"),
            "paragraphs": clean,
        })
    return result


def filter_search_results(search_results: list) -> list:
    """Only the highlight snippets are usable; drop all ES scoring/shard
    metadata. Snippets are short but can surface unexpected good sources."""
    seen = set()
    result = []
    for sr in search_results:
        hits = sr.get("data", {}).get("hits", {}).get("hits", [])
        for hit in hits:
            highlights = hit.get("highlight", {}).get("naive_lemmatizer", [])
            for h in highlights:
                clean = strip_html(h)
                if clean and clean not in seen:
                    seen.add(clean)
                    result.append({
                        "source_id": hit.get("_id"),
                        "snippet": clean,
                    })
    return result


def filter_bracha_file(raw: dict) -> dict:
    rel = raw.get("related", {})
    # related is keyed by sefaria ref, e.g. {"Berakhot 26b": {...}}
    link_candidates, topic_items = [], []
    for _ref, block in rel.items():
        link_candidates.extend(filter_links(block.get("links", [])))
        topic_items.extend(filter_topics(block.get("topics", [])))
        # sheets, manuscripts, notes, guides, media: intentionally dropped -
        # sheets are UGC metadata with no inline text and uncertain licensing,
        # the rest were empty or near-empty in practice.

    return {
        "bracha_id": raw.get("bracha_id"),
        "category_id": raw.get("category_id"),
        "name_hebrew": raw.get("name_hebrew"),
        "name_hungarian": raw.get("name_hungarian"),
        "keywords": raw.get("keywords"),
        "primary_text": filter_texts(raw.get("texts", [])),
        "topic_descriptions": topic_items,
        "link_candidates_for_followup_fetch": link_candidates,
        "search_snippets": filter_search_results(raw.get("search_results", [])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/raw", help="Directory with raw fetch_sefaria.py output")
    parser.add_argument("--output", default="data/filtered", help="Directory to write filtered JSON")
    parser.add_argument("--bracha", help="Only process a single bracha_id (filename stem)")
    args = parser.parse_args()

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = list(in_dir.rglob("*.json"))
    if args.bracha:
        files = [f for f in files if f.stem == args.bracha]

    print(f"{'bracha_id':<25} {'raw KB':>8} {'filtered KB':>12} {'reduction':>10}")
    print("-" * 60)

    for f in files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        filtered = filter_bracha_file(raw)

        out_path = out_dir / f.name
        out_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")

        raw_kb = f.stat().st_size / 1024
        filtered_kb = out_path.stat().st_size / 1024
        reduction = 1 - (filtered_kb / raw_kb) if raw_kb else 0
        print(f"{filtered.get('bracha_id', f.stem):<25} {raw_kb:>8.1f} {filtered_kb:>12.1f} {reduction:>9.1%}")


if __name__ == "__main__":
    main()
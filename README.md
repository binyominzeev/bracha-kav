# Bracha Kavana App

A Jewish prayer companion app that suggests short **kavana** (intention/reflection)
cards to users before or during specific blessings (*brachot*), Shema, Amidah,
Birkot HaShachar, and Pesukei D'Zimra.

> ⚠️ **Important policy:** The app never generates raw liturgical text or halachic
> content from scratch. All prayer text comes from verified sources (primarily the
> [Sefaria API](https://www.sefaria.org/developers)). Every AI-processed card
> carries a citation and a **human-review flag** before being marked "approved".

---

## Project structure

```
/data
  /categories.json        — seed data: bracha categories & Sefaria refs
  /raw/                   — raw Sefaria API responses (one JSON per bracha)
  /cards/                 — generated card JSON files (pre-DB-import)

/scripts
  fetch_sefaria.py        — Stage 1: fetch raw texts from Sefaria
  generate_cards.py       — Stage 2: AI card extraction/generation
  estimate_cost.py        — Stage 3: token/cost estimator
  load_db.py              — load categories + approved cards into SQLite

/db
  schema.sql              — table definitions
  bracha_app.db           — generated SQLite file (gitignored)

/backend
  main.py                 — FastAPI app (card browsing endpoints)
  models.py               — DB queries

/frontend
  index.html              — static HTML/JS browsing interface

/ai_providers
  base.py                 — abstract adapter interface
  factory.py              — provider factory (reads PROVIDER env var)
  openai_provider.py
  anthropic_provider.py
  gemini_provider.py
```

---

## Quick start

### 1. Clone & install

```bash
git clone <repo-url>
cd bracha-kav
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set PROVIDER, MODEL, and the matching API key
```

### 3. Stage 1 — Fetch Sefaria data

```bash
python scripts/fetch_sefaria.py
# Add --force to re-fetch, --category amidah for a single category
```

Review the console output (richness table) and the files in `data/raw/`.
**Do not proceed to Stage 2 until you are happy with the raw data.**

### 4. Stage 3 — Estimate AI cost (before Stage 2!)

```bash
python scripts/estimate_cost.py
python scripts/estimate_cost.py --sample   # estimate from 3 brachot, extrapolate
```

Verify the pricing table in `scripts/estimate_cost.py` is up to date before
making financial decisions.

### 5. Stage 2 — Generate kavana cards

```bash
python scripts/generate_cards.py
# Add --category or --bracha to process a subset first
```

Cards are saved to `data/cards/` with `approved: false` by default.

### 6. Load the database

```bash
python scripts/load_db.py --all   # loads all cards (approved + unapproved)
```

### 7. Run the backend

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 8. Open the frontend

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000) — the FastAPI server
serves `frontend/index.html` at the root.

You can also open `frontend/index.html` directly in a browser; it will try to
connect to `http://localhost:8000/api`.

---

## AI provider configuration

Set `PROVIDER` and `MODEL` in your `.env` file:

| Provider   | `PROVIDER=` | Example `MODEL=`      | Pricing page |
|------------|-------------|----------------------|--------------|
| OpenAI     | `openai`    | `gpt-4o-mini`        | [openai.com/pricing](https://openai.com/pricing) |
| Anthropic  | `anthropic` | `claude-haiku-3-5`   | [anthropic.com/pricing](https://www.anthropic.com/pricing) |
| Google     | `gemini`    | `gemini-1.5-flash`   | [ai.google.dev/pricing](https://ai.google.dev/pricing) |

---

## Development stages

| Stage | Script | Description |
|-------|--------|-------------|
| 1 | `fetch_sefaria.py` | Fetch raw Sefaria texts — **run this first** |
| 2 | `generate_cards.py` | AI card generation — run after reviewing Stage 1 |
| 3 | `estimate_cost.py` | Cost estimator — run before Stage 2 |
| 4 | Frontend | Card review UI at `http://localhost:8000` |

Recommendation algorithm and user authentication are **not yet implemented** —
they are planned for future stages.

---

## Database schema

See [`db/schema.sql`](db/schema.sql). Tables:
- `brachot` — blessing definitions
- `cards` — kavana cards (with approval status)
- `user_swipes` — (defined, not yet used)
- `user_preferences` — (defined, not yet used)

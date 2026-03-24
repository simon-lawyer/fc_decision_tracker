# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the web app (http://localhost:5001)
python app.py

# Run the pipeline (default: previous week)
python fc_report.py

# Specific date range
python fc_report.py --start-date 2026-03-09 --end-date 2026-03-15

# Dry run — search and filter only, no Claude API calls
python fc_report.py --dry-run

# Check database contents
python -c "from db import cases; print(cases.count)"
```

No test suite exists. Use `--dry-run` to verify search/filter logic without API costs.

## Architecture

Two entry points sharing a SQLite database (`data/cases.db`):

1. **Pipeline** (`fc_report.py`) — weekly batch job: search A2AJ API → filter to IMM cases → analyze with Claude → save to database → generate markdown report
2. **Web app** (`app.py`) — FastHTML + Monster UI browser for the accumulated case data

### Pipeline data flow

```
a2aj_client.search_fc_cases()     →  all FC cases (EN + FR, wildcard query)
a2aj_client.filter_imm_cases()    →  only IMM-docket cases
db_manager.get_processed_citations() → skip already-analyzed cases
a2aj_client.fetch_case_text()     →  full decision text (tries EN, falls back to FR)
case_analyzer.analyze_cases_concurrent() → Claude extracts structured data (3 concurrent)
  └─ on_case_done callback per case:
       normalizer.normalize_case()  → clean judge/nationality/lawyer names
       normalizer.reconcile()       → flag potential typos (edit distance)
       db_manager.save_cases()      → upsert to SQLite immediately
report_generator.generate_report() → markdown grouped by category
```

**Critical pattern: incremental saving.** Each case is saved to the database immediately after analysis via the `on_case_done` callback. If the pipeline crashes after case 10 of 15, those 10 are safe. Next run deduplicates by citation (the primary key) and picks up from case 11.

### Database layer

Two parallel representations of the same data:

- **`models.py`** — Pydantic models (`CaseExtraction`, `LegalIssue`) used for validation during extraction
- **`db.py`** — fastlite dataclass (`Case`) defining the SQLite table schema

`irpa_sections` and `legal_issues` are stored as JSON strings in SQLite. `db_manager.py` handles serialization on write and `app.py`'s `_row_to_dict()` handles deserialization on read.

The `db_manager.py` module exposes the same API the old CSV manager had: `load_master()`, `get_processed_citations()`, `save_cases()`. If you add a field to `CaseExtraction`, also add it to the `Case` dataclass in `db.py`.

### Web app

FastHTML with HTMX. Routes: `/` (case list), `/cases` (HTMX filtered results with infinite scroll), `/stats`, `/reset`. Filtering is AND logic across all non-empty fields. Clickable metadata (judge, category, nationality) sets the filter dropdown and submits the form via JavaScript.

## Key conventions

- **`lawyer_migrant`**: always the non-citizen's counsel (not "applicant" — the migrant may be respondent)
- **Judge names**: normalized to surname only (honorifics stripped by `normalizer.py`)
- **Nationality**: adjective→country conversion via lookup table (e.g., "Indian"→"India")
- **Disposition values**: `allowed`, `dismissed`, `granted_in_part` (exactly these strings)
- **Categories**: RAD, PRRA, RPD, IAD, H&C, Visa, ID Admissibility, Misrepresentation, Inadmissibility, Detention, Stay, Procedural, Other
- **Dates**: stored as `YYYY-MM-DD` strings (API returns ISO with timezone, we split on "T")
- **Bilingual**: search returns EN+FR cases; text fetch tries English first, falls back to French

## Deployment

Railway with nixpacks. `Procfile` and `railway.toml` are configured. The app reads `PORT` env var and binds to `0.0.0.0` in production. Live reload is disabled when `RAILWAY_ENVIRONMENT` or `PORT` is set. A persistent volume is needed at `data/` to preserve the SQLite database across deploys.

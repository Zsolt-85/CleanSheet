# CleanSheet

Clean your spreadsheet in seconds. Upload a messy Excel or CSV file — CleanSheet removes duplicates, fixes formatting, validates emails, normalizes dates, and shows you **every single change** in a downloadable report.

No sign-up. No stored files. No AI black box — only deterministic, explainable rules.

> **Status:** private beta. Core loop (upload → analyze → clean → download) is
> complete and covered by 70+ automated tests. See [Roadmap](#roadmap) for what
> comes next.

## What it cleans

- Empty rows (including rows full of `N/A`, `NULL`, `-` markers)
- Exact duplicate rows and duplicate emails
- Missing-value markers (`N/A`, `NULL`, `-`, …) → normalized to empty, originals logged
- Whitespace (leading/trailing/multi-space, tabs, newlines)
- Capitalization (title case with acronym and Romanian legal-form lists: SC, SRL, SA)
- Emails (validation, common typo-domain fixes like `gmial.com → gmail.com`)
- Dates (safe formats → ISO; ambiguous ones flagged, never guessed)
- Phones (formatting normalized, country never guessed, implausible flagged)
- Countries (names → ISO codes, e.g. `Romania → RO`)
- CSV delimiter auto-detection: comma, semicolon (EU Excel exports), tab, pipe

## Cleaning modes

Modes differ **only in judgment calls**. Everything else is identical.

| Operation | Conservative | Default (recommended) | Aggressive |
|-----------|--------------|----------------------|------------|
| Empty rows, exact dupes, email dupes, whitespace, safe dates | Yes | Yes | Yes |
| Capitalization | No | Yes | Yes |
| Ambiguous dates (`03/04/2026`) | Left + flagged | Left + flagged | Assumed MM/DD |
| Email typo fixes (`gmial.com`) | Suggested only | Applied | Applied |
| Phone normalization (country never guessed) | Yes | Yes | Yes |
| Country names → ISO codes | Yes | Yes | Yes |
| Invalid values | Kept + flagged | Kept + flagged | Kept + flagged |

**Always true, every mode:** every applied change is logged with reason and
confidence; invalid values are kept and flagged, never silently deleted;
removed rows are logged with full contents and recoverable from the report.

## Quick start

```bash
pip install -e ".[dev]"   # engine + CLI + tests
pip install -e ".[api]"   # + web app

# Command line
cleansheet clean messy.csv --output cleaned.xlsx --report report.xlsx
cleansheet analyze messy.csv
cleansheet modes          # what each mode does

# Web app (http://127.0.0.1:8000)
uvicorn backend.app:app --port 8000
```

The web UI is bilingual (English/Romanian, persisted switcher) and includes
`Privacy` and `Terms` pages (`/privacy`, `/terms`).

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Browser frontend |
| GET | `/api/health` | Liveness (also the Docker healthcheck) |
| GET | `/api/limits` | Upload limits |
| GET | `/api/modes` | Mode semantics + comparison (`?lang=ro` for Romanian) — single source of truth for the frontend |
| GET | `/api/stats` | Anonymous totals (completed cleanings, rows in/out, changes applied, jobs today) shown as a live beta count — always real, never inflated |
| POST | `/api/analyze` | Multipart `file` → profile, issues, suggested ops (nothing stored) |
| POST | `/api/clean` | Multipart `file` + `mode` + optional `email_column` → summary + download URLs |
| GET | `/api/download/{token}/{cleaned\|report}` | Single-use download; files auto-deleted, links expire after 30 min |
| GET | `/privacy`, `/terms` | Bilingual legal pages |

Design: no database, no auth, no secrets. Uploads capped at 25 MB / 50k rows /
200 columns. User errors return 400 with a friendly message; internal failures
return a generic 500. Per-IP rate limiting (120/min) and security headers are
built into the middleware. Result files live in the OS temp dir under
unguessable tokens.

## Deployment (Render free tier)

The repo includes `render.yaml`, so deployment is a Blueprint import:

1. Sign up at render.com with GitHub (no credit card).
2. Dashboard → **New +** → **Blueprint** → connect the `Zsolt-85/CleanSheet` repo.
3. Render reads `render.yaml` and creates the `cleansheet` web service — just Apply.
4. Wait for the build (~3–5 min) → open the `*.onrender.com` URL.

Free-tier facts: single instance (matches how the app was tested), sleeps
after 15 min idle (first visit wakes it in ~1 min), 750 instance-hours/month.
The SQLite stats file lives in temp storage and resets on redeploy — but
every analyze/clean also writes one anonymous log line
(`event=clean mode=default rows_before=20 …`, never filenames), so filter
the dashboard's Logs tab for `cleansheet-stats` to see real usage across
restarts. Revisit persistent storage when usage justifies it.

## Docker (alternative / Cloud Run)

```bash
docker build -t cleansheet .
docker run -p 8000:8000 cleansheet
# or with the host-provided port: docker run -e PORT=8080 -p 8080:8080 cleansheet
```

Notes for hosting (Fly.io, Render, etc.):

- Single container, single worker (`--workers 1` default): rate limits and
  download tokens are in-memory per process. Scale vertically for beta.
- The container honors the `PORT` environment variable and exposes
  `/api/health` for health checks.
- HTTPS is provided by the host. No environment variables or secrets required.

## Project structure

```
cleansheet/
├── cleaning_engine/       # Independent cleaning library (no web deps)
│   ├── loader.py          # CSV/XLSX loading, encoding + delimiter detection
│   ├── profiler.py        # Profiling, column-type inference, issue analysis
│   ├── duplicates.py      # Duplicate row / email handling
│   ├── emails.py          # Email validation + typo fixes
│   ├── whitespace.py      # Whitespace normalization
│   ├── capitalization.py  # Title-casing with acronym lists
│   ├── dates.py           # Safe date normalization
│   ├── normalization.py   # Nulls, missing markers, empty rows, countries
│   ├── phones.py          # Phone normalization (country never guessed)
│   ├── change_tracker.py  # Per-change records with reason + confidence
│   ├── exporter.py        # Cleaned file + multi-sheet report export
│   ├── modes.py           # Mode semantics (EN/RO, single source of truth)
│   ├── pipeline.py        # Pipeline orchestration (default/conservative/aggressive)
│   └── cli.py             # CLI: clean, analyze, modes, stats, version
├── backend/
│   ├── app.py             # FastAPI: analyze/clean/download/modes/legal
│   ├── stats.py           # Anonymous aggregate counters (SQLite)
│   └── static/            # Single-file bilingual frontend + legal pages
├── assets/                # Generated marketing images (see assets/README.md)
├── tools/                 # Generator scripts for demo data + assets
├── tests/
│   ├── fixtures/input/    # Messy sample files (incl. semicolon CSV + upload demos)
│   ├── fixtures/expected/ # Frozen golden outputs (regression-tested)
│   ├── test_cleaning_engine.py
│   └── test_api.py
├── Dockerfile
└── pyproject.toml
```

## Development

```bash
pytest                    # full suite (engine + API + golden fixtures)
ruff check cleaning_engine backend tests
ruff format cleaning_engine backend tests
mypy cleaning_engine
```

Golden fixtures: `tests/fixtures/expected/` holds human-reviewed outputs.
If a pipeline change alters them, review the diff before re-freezing.

## Roadmap

Product and business strategy (phases, monetization, marketing):
[Spread sheet cleaner.txt](../Spread%20sheet%20cleaner.txt)

## License

MIT — see [LICENSE](LICENSE).

"""CleanSheet web backend (Phase 2 MVP).

Design (per roadmap: no DB, no auth, temp processing + auto-delete):
- POST /api/analyze: upload a file, get profile + issues + suggested ops (nothing stored)
- POST /api/clean: upload a file + options, get summary + tokenized download URLs
- GET /api/download/{token}/{kind}: download cleaned.xlsx or report.xlsx,
  each file deleted right after serving; entries expire after RESULT_TTL_SECONDS
- GET /: minimal frontend; GET /api/health: liveness

Security posture:
- Extension + size + dimension limits enforced before processing
- User errors (bad file) -> 400 with friendly message; system errors -> 500 generic
- Simple in-memory per-IP rate limit (no extra dependency)
- Security response headers (nosniff, deny framing, minimal referrer)
"""

from __future__ import annotations

import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.stats import get_stats, incr, record_cleaning
from cleaning_engine import (
    CleaningPipeline,
    analyze_spreadsheet,
    export_cleaned,
    export_report,
    load_spreadsheet_from_bytes,
    profile_spreadsheet,
)
from cleaning_engine.loader import (
    MAX_COLUMNS,
    MAX_FILE_SIZE_MB,
    MAX_ROWS,
    SUPPORTED_EXTENSIONS,
    SpreadsheetLoadError,
)
from cleaning_engine.modes import build_pipeline, get_modes_content

MAX_UPLOAD_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
RESULT_TTL_SECONDS = 30 * 60  # download links live 30 minutes, then wiped
RATE_LIMIT_PER_MINUTE = 120

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CleanSheet", version="0.1.0")

# token -> {"cleaned": Path, "report": Path, "expires": float}
_results: dict[str, dict[str, Any]] = {}
# ip -> list[timestamps]
_rate_buckets: dict[str, list[float]] = {}


@app.middleware("http")
async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # --- rate limit (fixed window, per IP, in-memory) ---
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _rate_buckets.get(ip, [])
    bucket = [t for t in bucket if now - t < 60]
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse({"detail": "Rate limit exceeded, try again later."}, status_code=429)
    bucket.append(now)
    _rate_buckets[ip] = bucket

    _sweep_expired_results()

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _sweep_expired_results() -> None:
    now = time.time()
    expired = [t for t, r in _results.items() if r["expires"] < now]
    for token in expired:
        _delete_result(token)


def _delete_result(token: str) -> None:
    entry = _results.pop(token, None)
    if not entry:
        return
    for key in ("cleaned", "report"):
        try:
            Path(entry[key]).unlink(missing_ok=True)
        except OSError:
            pass


async def _read_upload_capped(file: UploadFile) -> bytes:
    """Read upload, enforcing the size cap (read one byte past the cap to detect overflow)."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_FILE_SIZE_MB} MB).",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return content


def _load_or_400(content: bytes, filename: str):  # type: ignore[no-untyped-def]
    try:
        return load_spreadsheet_from_bytes(content, filename or "upload.csv")
    except SpreadsheetLoadError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _build_pipeline(mode: str, email_column: str | None) -> CleaningPipeline:
    try:
        return build_pipeline(mode, email_column)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/limits")
def limits() -> dict[str, Any]:
    return {
        "max_file_mb": MAX_FILE_SIZE_MB,
        "max_rows": MAX_ROWS,
        "max_columns": MAX_COLUMNS,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


@app.get("/api/modes")
def modes(lang: str = "en") -> dict[str, Any]:
    """Cleaning-mode semantics (single source of truth for frontend/CLI/docs)."""
    return get_modes_content(lang)


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await _read_upload_capped(file)
    data = _load_or_400(content, file.filename or "upload.csv")

    # Profile + analyze without cleaning (read-only; nothing stored)
    prof = profile_spreadsheet(data)
    analysis = analyze_spreadsheet(data, prof)

    # Keep the response small: cap issue examples per key
    issues = {k: v[:10] for k, v in analysis.issues.items()}
    issue_counts = {k: len(v) for k, v in analysis.issues.items()}

    # Value-frequency facets (OpenRefine-style): top values per column so
    # users can spot inconsistencies at a glance. Missing markers excluded.
    facets = []
    for col in data.dataframe.columns[:50]:
        series = data.dataframe[col].dropna().astype(str)
        series = series[series.str.strip() != ""].head(1000)
        top = series.value_counts().head(8)
        facets.append(
            {
                "name": str(col),
                "unique": int(series.nunique()),
                "values": [{"value": str(v), "count": int(c)} for v, c in top.items()],
            }
        )

    incr("analyze_calls")
    return {
        "filename": data.filename,
        "rows": prof.shape[0],
        "columns": prof.shape[1],
        "empty_rows": prof.empty_rows,
        "duplicate_rows": prof.duplicate_rows,
        "empty_cells": prof.empty_cells,
        "column_types": [
            {"name": c.name, "inferred_type": c.inferred_type.value, "nulls": c.null_count}
            for c in prof.columns
        ],
        "issue_counts": issue_counts,
        "issue_examples": issues,
        "facets": facets,
        "suggested_operations": analysis.suggested_operations,
    }


@app.post("/api/clean")
async def clean(
    file: UploadFile = File(...),
    mode: str = Form("default"),
    email_column: str | None = Form(None),
) -> dict[str, Any]:
    content = await _read_upload_capped(file)
    data = _load_or_400(content, file.filename or "upload.csv")
    pipeline = _build_pipeline(mode, email_column)

    try:
        cleaned_data, tracker = pipeline.run(data)
    except Exception:
        # System error: generic message, no internals leaked
        raise HTTPException(status_code=500, detail="Cleaning failed due to an internal error.")

    report = tracker.to_report()
    tmpdir = Path(tempfile.gettempdir()) / "cleansheet"
    tmpdir.mkdir(exist_ok=True)
    token = secrets.token_urlsafe(24)
    # data.filename is already sanitized by the loader; on-disk names stay
    # unique via token, download names stay human-readable.
    stem = Path(data.filename).stem[:50] or "cleaned"
    cleaned_path = tmpdir / f"{stem}_{token}_cleaned.xlsx"
    report_path = tmpdir / f"{stem}_{token}_report.xlsx"
    try:
        # Reuse the engine's exporter: cleaned file + multi-sheet
        # report (Changes / Summary / By Rule)
        export_cleaned(cleaned_data, cleaned_path)
        export_report(report, report_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to generate output files.")

    _results[token] = {
        "cleaned": cleaned_path,
        "report": report_path,
        "cleaned_name": f"{stem}_cleaned.xlsx",
        "report_name": f"{stem}_report.xlsx",
        "expires": time.time() + RESULT_TTL_SECONDS,
    }

    applied = sum(1 for c in report.changes if c.applied)
    rows_before = data.dataframe.shape[0]
    rows_after = cleaned_data.dataframe.shape[0]
    try:
        record_cleaning(rows_before, rows_after, applied)
    except Exception:
        # Telemetry must never break a cleaning request.
        pass
    return {
        "filename": data.filename,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "total_changes": len(report.changes),
        "applied_changes": applied,
        "by_rule": dict(sorted(report.summary.items(), key=lambda kv: -kv[1])),
        "processing_time_ms": round(report.processing_time_ms, 1),
        "download_cleaned_url": f"/api/download/{token}/cleaned",
        "download_report_url": f"/api/download/{token}/report",
        "expires_in_seconds": RESULT_TTL_SECONDS,
    }


PUBLIC_STATS_KEYS = ("jobs_completed", "rows_in", "rows_out", "changes_applied", "jobs_today")


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    """Public subset of the anonymous totals: what the frontend counter shows.
    Funnel internals (page views, per-endpoint calls) are deliberately NOT
    exposed over HTTP - founders read them via `cleansheet stats` instead."""
    full = get_stats()
    return {k: full[k] for k in PUBLIC_STATS_KEYS}


@app.get("/api/download/{token}/{kind}")
def download(token: str, kind: str):  # type: ignore[no-untyped-def]
    if kind not in ("cleaned", "report"):
        raise HTTPException(status_code=404, detail="Unknown download kind.")
    entry = _results.get(token)
    if not entry or entry["expires"] < time.time():
        _delete_result(token)
        raise HTTPException(status_code=404, detail="Download link expired or invalid.")
    path: Path = entry[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File no longer available.")

    filename = str(entry.get(f"{kind}_name", f"cleansheet_{kind}.xlsx"))
    incr("download_hits")
    # Serve then delete this file; drop the token entry once both are gone
    response = FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

    def _cleanup() -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        remaining = [k for k in ("cleaned", "report") if Path(entry[k]).exists()]
        if not remaining:
            _results.pop(token, None)

    # Background task would be cleaner, but a simple approach: register cleanup
    # via response.background (starlette supports it on FileResponse)
    from starlette.background import BackgroundTask

    response.background = BackgroundTask(_cleanup)
    return response


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    incr("page_views")
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>CleanSheet API</h1><p>Frontend not built yet. See /docs.</p>"


def _static_page(name: str, fallback_title: str) -> str:
    page = STATIC_DIR / name
    if page.exists():
        return page.read_text(encoding="utf-8")
    return f"<h1>{fallback_title}</h1>"


@app.get("/privacy", response_class=HTMLResponse)
def privacy() -> str:
    return _static_page("privacy.html", "Privacy Policy")


@app.get("/terms", response_class=HTMLResponse)
def terms() -> str:
    return _static_page("terms.html", "Terms of Use")

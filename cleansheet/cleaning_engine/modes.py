"""Cleaning-mode semantics (single source of truth).

The three modes differ only in how they treat *judgment calls*:
capitalization, ambiguous dates and email-typo guesses. Everything else
(empty rows, exact duplicates, duplicate emails, whitespace, safe dates)
is identical. The backend (/api/modes), the CLI (cleansheet modes) and
the README all render from the structures below, so the descriptions
can't drift from what the pipelines actually do.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cleaning_engine.pipeline import CleaningPipeline


def _factory(name: str) -> Callable[[], CleaningPipeline]:
    from cleaning_engine import pipeline as _pipeline

    return getattr(_pipeline, f"create_{name}_pipeline")


MODES: dict[str, dict[str, Any]] = {
    "conservative": {
        "name": "Conservative",
        "tagline": "Only fixes the engine is sure about. Everything judgmental is suggested, not applied.",
        "details": [
            "Removes empty rows, exact duplicate rows and duplicate emails.",
            "Fixes whitespace and safe, unambiguous dates.",
            "Does NOT change capitalization.",
            "Does NOT fix email typos (e.g. gmial.com) - suggests them for your review instead.",
            "Keeps invalid values and ambiguous dates, flagged in the report.",
        ],
    },
    "default": {
        "name": "Default",
        "tagline": "The recommended balance: thorough cleanup, no guessing on ambiguous data.",
        "details": [
            "Everything Conservative does, plus capitalization normalization.",
            "Fixes common email typos (e.g. gmial.com becomes gmail.com).",
            "Ambiguous dates (03/04/2026 could be March 4 or April 3) are left alone and flagged.",
            "Invalid values are kept and flagged, never silently deleted.",
        ],
    },
    "aggressive": {
        "name": "Aggressive",
        "tagline": "Maximum uniformity. Assumes ambiguous numeric dates are month-first.",
        "details": [
            "Everything Default does, plus ambiguous numeric dates are normalized assuming MM/DD/YYYY.",
            "Only use when you know your data is month-first - otherwise dates can be silently misread.",
            "Invalid values are still kept and flagged, never silently deleted.",
        ],
        "warning": "Assumes MM/DD/YYYY. If your data is day-first (DD/MM/YYYY), dates like 03/04/2026 will be misread as March 4.",
    },
}

# Operation-by-operation comparison, rendered as a table in the frontend/CLI.
MODE_COMPARISON: list[dict[str, str]] = [
    {"operation": "Remove empty rows", "conservative": "Yes", "default": "Yes", "aggressive": "Yes"},
    {
        "operation": "Remove exact duplicate rows",
        "conservative": "Yes",
        "default": "Yes",
        "aggressive": "Yes",
    },
    {
        "operation": "Remove duplicate emails",
        "conservative": "Yes",
        "default": "Yes",
        "aggressive": "Yes",
    },
    {"operation": "Fix whitespace", "conservative": "Yes", "default": "Yes", "aggressive": "Yes"},
    {
        "operation": "Normalize capitalization",
        "conservative": "No",
        "default": "Yes",
        "aggressive": "Yes",
    },
    {"operation": "Normalize safe dates", "conservative": "Yes", "default": "Yes", "aggressive": "Yes"},
    {
        "operation": "Ambiguous dates (03/04/2026)",
        "conservative": "Left + flagged",
        "default": "Left + flagged",
        "aggressive": "Assumed MM/DD",
    },
    {
        "operation": "Email typo fixes (gmial.com)",
        "conservative": "Suggested only",
        "default": "Applied",
        "aggressive": "Applied",
    },
    {
        "operation": "Invalid values",
        "conservative": "Kept + flagged",
        "default": "Kept + flagged",
        "aggressive": "Kept + flagged",
    },
]

MODES_RO: dict[str, dict[str, Any]] = {
    "conservative": {
        "name": "Conservator",
        "tagline": "Corectează doar ce este sigur. Tot ce ține de interpretare este sugerat, nu aplicat.",
        "details": [
            "Elimină rândurile goale, duplicatele exacte și adresele de email duplicate.",
            "Corectează spațiile albe și datele calendaristice sigure, fără ambiguitate.",
            "NU modifică scrierea cu majuscule.",
            "NU corectează greșelile de tipar din emailuri (ex. gmial.com) - le sugerează pentru verificare.",
            "Păstrează valorile invalide și datele ambigue, marcate în raport.",
        ],
    },
    "default": {
        "name": "Standard",
        "tagline": "Echilibrul recomandat: curățare temeinică, fără presupuneri pe date ambigue.",
        "details": [
            "Tot ce face modul Conservator, plus normalizarea majusculelor.",
            "Corectează greșelile frecvente din emailuri (ex. gmial.com devine gmail.com).",
            "Datele ambigue (03/04/2026 poate fi 3 aprilie sau 4 martie) sunt lăsate nemodificate și marcate.",
            "Valorile invalide sunt păstrate și marcate, niciodată șterse pe ascuns.",
        ],
    },
    "aggressive": {
        "name": "Agresiv",
        "tagline": "Uniformitate maximă. Presupune că datele numerice ambigue sunt lună-zi.",
        "details": [
            "Tot ce face modul Standard, plus datele numerice ambigue sunt normalizate presupunând LL/ZZ/AAAA.",
            "Folosește-l doar dacă știi că datele tale sunt lună-zi - altfel datele pot fi interpretate greșit.",
            "Valorile invalide sunt tot păstrate și marcate, niciodată șterse pe ascuns.",
        ],
        "warning": "Presupune LL/ZZ/AAAA. Dacă datele tale sunt zi-lună (ZZ/LL/AAAA), date ca 03/04/2026 vor fi interpretate greșit ca 4 martie.",
    },
}

MODE_COMPARISON_RO: list[dict[str, str]] = [
    {"operation": "Elimină rândurile goale", "conservative": "Da", "default": "Da", "aggressive": "Da"},
    {
        "operation": "Elimină rândurile duplicat exacte",
        "conservative": "Da",
        "default": "Da",
        "aggressive": "Da",
    },
    {
        "operation": "Elimină adresele de email duplicate",
        "conservative": "Da",
        "default": "Da",
        "aggressive": "Da",
    },
    {"operation": "Corectează spațiile albe", "conservative": "Da", "default": "Da", "aggressive": "Da"},
    {
        "operation": "Normalizează majusculele",
        "conservative": "Nu",
        "default": "Da",
        "aggressive": "Da",
    },
    {"operation": "Normalizează datele sigure", "conservative": "Da", "default": "Da", "aggressive": "Da"},
    {
        "operation": "Date ambigue (03/04/2026)",
        "conservative": "Lăsate + marcate",
        "default": "Lăsate + marcate",
        "aggressive": "Presupus LL/ZZ",
    },
    {
        "operation": "Corecturi typo email (gmial.com)",
        "conservative": "Doar sugerate",
        "default": "Aplicate",
        "aggressive": "Aplicate",
    },
    {
        "operation": "Valori invalide",
        "conservative": "Păstrate + marcate",
        "default": "Păstrate + marcate",
        "aggressive": "Păstrate + marcate",
    },
]

GUARANTEES: list[str] = [
    "Every applied change is logged in the report with row, reason and confidence.",
    "Invalid values are kept and flagged, never silently deleted.",
    "Removed rows (duplicates, empty) are logged with full contents and can be recovered from the report.",
    "Files are processed temporarily and deleted after download or after 30 minutes.",
]

GUARANTEES_RO: list[str] = [
    "Fiecare modificare aplicată este înregistrată în raport, cu rând, motiv și nivel de încredere.",
    "Valorile invalide sunt păstrate și marcate, niciodată șterse pe ascuns.",
    "Rândurile eliminate (duplicate, goale) sunt înregistrate integral și pot fi recuperate din raport.",
    "Fișierele sunt procesate temporar și șterse după descărcare sau după 30 de minute.",
]

MODE_IDS: tuple[str, ...] = ("conservative", "default", "aggressive")


def get_modes_content(lang: str = "en") -> dict[str, Any]:
    """Modes + comparison + guarantees in the requested language ('en'/'ro')."""
    ro = lang.lower().startswith("ro")
    modes = MODES_RO if ro else MODES
    comparison = MODE_COMPARISON_RO if ro else MODE_COMPARISON
    return {
        "default_mode": "default",
        "lang": "ro" if ro else "en",
        "modes": [{"id": mode_id, **info} for mode_id, info in modes.items()],
        "comparison": comparison,
        "guarantees": GUARANTEES_RO if ro else GUARANTEES,
    }


def build_pipeline(mode: str, email_column: str | None = None) -> CleaningPipeline:
    """Create a pipeline for a mode id. Raises ValueError on unknown mode."""
    if mode not in MODE_IDS:
        raise ValueError(f"Unknown mode: {mode!r}. Choose from: {', '.join(MODE_IDS)}")
    pipeline = _factory(mode)()
    if email_column:
        pipeline.config.email_column = email_column
    return pipeline

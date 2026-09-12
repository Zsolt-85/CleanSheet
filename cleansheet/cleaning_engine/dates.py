"""Date normalization."""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel

# Date formats to try parsing
DATE_FORMATS = [
    "%Y-%m-%d",  # 2026-02-01
    "%m/%d/%Y",  # 02/01/2026
    "%m-%d-%Y",  # 02-01-2026
    "%d.%m.%Y",  # 01.02.2026
    "%d/%m/%Y",  # 01/02/2026
    "%B %d, %Y",  # February 1, 2026
    "%b %d, %Y",  # Feb 1, 2026
    "%d %B %Y",  # 1 February 2026
    "%d %b %Y",  # 1 Feb 2026
    "%Y/%m/%d",  # 2026/02/01
    "%m.%d.%Y",  # 02.01.2026
]

OUTPUT_FORMAT = "%Y-%m-%d"  # ISO 8601


def parse_date(text: str) -> pd.Timestamp | None:
    """
    Try to parse a date string using multiple formats.

    Returns:
        pd.Timestamp if successful, None otherwise
    """
    if not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return pd.Timestamp(dt)
        except ValueError:
            continue

    # Try pandas flexible parser as last resort
    try:
        return pd.Timestamp(text)
    except (ValueError, TypeError):
        return None


def normalize_date(text: str, output_format: str = OUTPUT_FORMAT) -> str | None:
    """
    Normalize a date string to ISO format.

    Returns:
        Normalized date string or None if unparseable
    """
    parsed = parse_date(text)
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.strftime(output_format)


def is_safe_to_normalize(original: str, normalized: str) -> bool:
    """
    Check if date normalization is safe (no ambiguity).

    For example, 01/02/2026 could be Jan 2 or Feb 1.
    We consider it unsafe if day <= 12 and month <= 12.
    """
    if not original or not normalized:
        return False

    # If already in ISO format, it's safe
    if re.match(r"^\d{4}-\d{2}-\d{2}$", original.strip()):
        return True

    # Check for ambiguous formats
    # MM/DD/YYYY or DD/MM/YYYY where both <= 12
    ambiguous_patterns = [
        r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$",  # 01/02/2026
    ]

    for pattern in ambiguous_patterns:
        match = re.match(pattern, original.strip())
        if match:
            part1, part2 = int(match.group(1)), int(match.group(2))
            if part1 <= 12 and part2 <= 12:
                return False  # Ambiguous

    return True


def normalize_dates_column(
    df: pd.DataFrame,
    column: str,
    tracker: ChangeTracker,
    output_format: str = OUTPUT_FORMAT,
    rule_name: str = "normalize_dates",
    only_safe: bool = True,
) -> pd.DataFrame:
    """
    Normalize dates in a specific column.

    Args:
        df: Input DataFrame
        column: Column name to normalize
        tracker: ChangeTracker to record changes
        output_format: Output date format
        rule_name: Name of the rule for tracking
        only_safe: Only normalize unambiguous dates

    Returns:
        DataFrame with normalized dates
    """
    if column not in df.columns:
        return df

    original_series = df[column].copy()

    for idx, value in original_series.items():
        if pd.isna(value) or str(value).strip() == "":
            continue

        original = str(value)
        normalized = normalize_date(original, output_format)

        if normalized is None:
            continue

        if only_safe and not is_safe_to_normalize(original, normalized):
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=normalized,
                    reason=f"Ambiguous date format - not auto-normalized (would be {normalized})",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.LOW,
                    applied=False,
                )
            )
            continue

        if normalized != original:
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=normalized,
                    reason=f"Date normalized to {output_format}",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.HIGH,
                    applied=True,
                )
            )
            df.at[idx, column] = normalized

    return df


def normalize_all_dates(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    output_format: str = OUTPUT_FORMAT,
    rule_name: str = "normalize_dates",
    only_safe: bool = True,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Normalize dates in all detected date columns (or specified columns).

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        output_format: Output date format
        rule_name: Name of the rule for tracking
        only_safe: Only normalize unambiguous dates
        columns: Specific columns to normalize

    Returns:
        DataFrame with normalized dates
    """
    if columns is None:
        # Try to detect date columns by attempting to parse
        columns = []
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().astype(str).str.strip().head(20)
            if len(sample) == 0:
                continue
            parseable = sample.apply(parse_date).notna().sum()
            if parseable / len(sample) > 0.5:
                columns.append(col)

    for col in columns:
        df = normalize_dates_column(df, col, tracker, output_format, rule_name, only_safe)

    return df

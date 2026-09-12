"""Whitespace normalization."""

from __future__ import annotations

import re

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in a string:
    - Strip leading/trailing whitespace
    - Collapse multiple internal spaces to single space
    - Normalize tabs and newlines to spaces
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""

    # Replace tabs, newlines, carriage returns with space
    text = re.sub(r"[\t\r\n]+", " ", text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    # Strip
    return text.strip()


def normalize_whitespace_column(
    df: pd.DataFrame,
    column: str,
    tracker: ChangeTracker,
    rule_name: str = "normalize_whitespace",
) -> pd.DataFrame:
    """
    Normalize whitespace in a specific column.

    Args:
        df: Input DataFrame
        column: Column name to normalize
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with normalized whitespace
    """
    if column not in df.columns:
        return df

    original_series = df[column].copy()

    for idx, value in original_series.items():
        if pd.isna(value):
            continue

        original = str(value)
        normalized = normalize_whitespace(original)

        if normalized != original:
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=normalized,
                    reason="Whitespace normalized",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.HIGH,
                    applied=True,
                )
            )
            df.at[idx, column] = normalized

    return df


def normalize_all_whitespace(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    rule_name: str = "normalize_whitespace",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Normalize whitespace in all string columns (or specified columns).

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking
        columns: Specific columns to normalize (default: all object/string columns)

    Returns:
        DataFrame with normalized whitespace
    """
    if columns is None:
        columns = df.select_dtypes(include=["object", "string"]).columns.tolist()

    for col in columns:
        df = normalize_whitespace_column(df, col, tracker, rule_name)

    return df

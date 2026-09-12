"""Capitalization normalization."""

from __future__ import annotations

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel

# Words that should remain lowercase in title case
LOWERCASE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "if",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "so",
    "the",
    "to",
    "up",
    "yet",
    "via",
    "vs",
}

# Words that should remain uppercase
UPPERCASE_WORDS = {
    "usa",
    "uk",
    "eu",
    "ceo",
    "cto",
    "cfo",
    "coo",
    "vp",
    "svp",
    "evp",
    "hr",
    "it",
    "ai",
    "ml",
    "api",
    "ui",
    "ux",
    "seo",
    "crm",
    "erp",
    "llc",
    "inc",
    "corp",
    "ltd",
    "plc",
    "gmbh",
    "ag",
    "sa",
    "nv",
    "ibm",
    "hp",
    "dell",
    "intel",
    "amd",
    "nvidia",
    # Romanian company legal forms (Societate Comerciala, SRL/SA always uppercase)
    "sc",
    "srl",
    "srl-d",
    "snc",
    "sca",
}


def to_title_case(text: str) -> str:
    """
    Convert to title case with smart handling of special words.
    """
    if not text:
        return text

    words = text.split()
    result = []

    for i, word in enumerate(words):
        lower = word.lower()

        # Check for uppercase acronyms FIRST (before first/last word rule).
        # Strip a trailing period so "Ltd." matches "ltd" -> "LTD."
        # (keeps "Acme LTD." consistent with "Globex CORP").
        if lower.rstrip(".") in UPPERCASE_WORDS:
            result.append(word.upper())
        # Handle hyphenated words before the first/last rule, so the
        # first/last capitalize() doesn't flatten them ("Weyland-Yutani"
        # would otherwise become "Weyland-yutani").
        elif "-" in word:
            parts = word.split("-")
            result.append(
                "-".join(
                    p.upper()
                    if p.lower().rstrip(".") in UPPERCASE_WORDS
                    else p.lower()
                    if p.lower() in LOWERCASE_WORDS
                    else p.capitalize()
                    for p in parts
                )
            )
        # First and last word always capitalized (if not an acronym)
        elif i == 0 or i == len(words) - 1:
            result.append(word.capitalize())
        # Check for lowercase words
        elif lower in LOWERCASE_WORDS:
            result.append(lower)
        else:
            result.append(word.capitalize())

    return " ".join(result)


def to_lower_case(text: str) -> str:
    """Convert to lowercase."""
    return text.lower() if isinstance(text, str) else str(text).lower()


def to_upper_case(text: str) -> str:
    """Convert to uppercase."""
    return text.upper() if isinstance(text, str) else str(text).upper()


def normalize_capitalization_column(
    df: pd.DataFrame,
    column: str,
    tracker: ChangeTracker,
    mode: str = "title",  # "title", "lower", "upper"
    rule_name: str = "normalize_capitalization",
) -> pd.DataFrame:
    """
    Normalize capitalization in a specific column.

    Args:
        df: Input DataFrame
        column: Column name to normalize
        tracker: ChangeTracker to record changes
        mode: 'title', 'lower', or 'upper'
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with normalized capitalization
    """
    if column not in df.columns:
        return df

    if mode == "title":
        normalize_func = to_title_case
        reason = "Capitalization normalized to title case"
    elif mode == "lower":
        normalize_func = to_lower_case
        reason = "Capitalization normalized to lowercase"
    elif mode == "upper":
        normalize_func = to_upper_case
        reason = "Capitalization normalized to uppercase"
    else:
        raise ValueError(f"Invalid mode: {mode}. Use 'title', 'lower', or 'upper'")

    original_series = df[column].copy()

    for idx, value in original_series.items():
        if pd.isna(value) or str(value).strip() == "":
            continue

        original = str(value)
        normalized = normalize_func(original)

        if normalized != original:
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=normalized,
                    reason=reason,
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.MEDIUM,  # Capitalization changes are subjective
                    applied=True,
                )
            )
            df.at[idx, column] = normalized

    return df


def normalize_all_capitalization(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    mode: str = "title",
    rule_name: str = "normalize_capitalization",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Normalize capitalization in all string columns (or specified columns).

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        mode: 'title', 'lower', or 'upper'
        rule_name: Name of the rule for tracking
        columns: Specific columns to normalize

    Returns:
        DataFrame with normalized capitalization
    """
    if columns is None:
        columns = df.select_dtypes(include=["object", "string"]).columns.tolist()

    for col in columns:
        df = normalize_capitalization_column(df, col, tracker, mode, rule_name)

    return df

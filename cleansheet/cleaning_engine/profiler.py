"""Spreadsheet profiling and analysis."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from cleaning_engine.models import (
    AnalysisResult,
    ColumnProfile,
    ColumnType,
    SpreadsheetData,
    SpreadsheetProfile,
)
from cleaning_engine.normalization import is_missing_value

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[\d\s\-\+\(\)]{7,}$")
DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),  # MM/DD/YYYY
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),  # MM-DD-YYYY
    re.compile(r"^\d{2}\.\d{2}\.\d{4}$"),  # DD.MM.YYYY
    re.compile(r"^[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}$"),  # Month DD, YYYY
]


def _infer_column_type(series: pd.Series, sample_size: int = 100) -> ColumnType:
    """Infer semantic type of a column from sample values."""
    non_null = series[~series.map(is_missing_value)]
    if len(non_null) == 0:
        return ColumnType.UNKNOWN

    sample = non_null.head(sample_size).astype(str).str.strip()
    sample = sample[sample != ""]

    if len(sample) == 0:
        return ColumnType.TEXT

    # Check email
    email_matches = sample.apply(lambda x: bool(EMAIL_PATTERN.match(x))).sum()
    if email_matches / len(sample) > 0.5:
        return ColumnType.EMAIL

    # Check date BEFORE phone: ISO dates like 2026-01-15 otherwise
    # match the loose phone regex (digits + dashes)
    date_matches = 0
    for pattern in DATE_PATTERNS:
        date_matches += sample.apply(lambda x: bool(pattern.match(x))).sum()
    if date_matches / len(sample) > 0.5:
        return ColumnType.DATE

    # Check phone (regex + at least 7 digits, so dates/years don't match)
    def _looks_like_phone(x: str) -> bool:
        if not bool(PHONE_PATTERN.match(x)):
            return False
        digits = re.sub(r"\D", "", x)
        return len(digits) >= 7

    phone_matches = sample.apply(_looks_like_phone).sum()
    if phone_matches / len(sample) > 0.5:
        return ColumnType.PHONE

    # Check company-like BEFORE name-like: "Acme Ltd." is titlecase with
    # a space, so the generic name check would claim it first. Keywords
    # are the more specific signal.
    company_keywords = ["ltd", "inc", "corp", "llc", "gmbh", "co.", "company"]
    company_like = sample.apply(lambda x: any(kw in x.lower() for kw in company_keywords)).sum()
    if company_like / len(sample) > 0.3:
        return ColumnType.COMPANY

    # Check name-like (contains space, proper case)
    name_like = sample.apply(lambda x: " " in x and x.istitle()).sum()
    if name_like / len(sample) > 0.3:
        return ColumnType.NAME

    # Check numeric
    numeric_like = pd.to_numeric(sample, errors="coerce").notna().sum()
    if numeric_like / len(sample) > 0.8:
        return ColumnType.NUMERIC

    # Check category (low cardinality)
    unique_ratio = len(sample.unique()) / len(sample)
    if unique_ratio < 0.1 and len(sample) > 10:
        return ColumnType.CATEGORY

    return ColumnType.TEXT


def _compute_column_stats(series: pd.Series, col_type: ColumnType) -> dict[str, Any]:
    """Compute statistics for a column based on its type."""
    stats = {}
    non_null = series[~series.map(is_missing_value)]
    non_null_str = non_null.astype(str).str.strip()
    non_null_str = non_null_str[non_null_str != ""]

    stats["min_length"] = int(non_null_str.str.len().min()) if len(non_null_str) > 0 else 0
    stats["max_length"] = int(non_null_str.str.len().max()) if len(non_null_str) > 0 else 0
    stats["avg_length"] = float(non_null_str.str.len().mean()) if len(non_null_str) > 0 else 0.0

    if col_type == ColumnType.EMAIL:
        domain_counts = non_null_str.str.split("@").str[1].value_counts().head(10)
        stats["top_domains"] = domain_counts.to_dict()
    elif col_type == ColumnType.DATE:
        # Try to parse dates
        parsed = pd.to_datetime(non_null_str, errors="coerce")
        stats["parsable_count"] = int(parsed.notna().sum())
        stats["date_range"] = {
            "min": str(parsed.min()) if parsed.notna().any() else None,
            "max": str(parsed.max()) if parsed.notna().any() else None,
        }
    elif col_type == ColumnType.NUMERIC:
        numeric = pd.to_numeric(non_null_str, errors="coerce")
        stats["min"] = float(numeric.min()) if numeric.notna().any() else None
        stats["max"] = float(numeric.max()) if numeric.notna().any() else None
        stats["mean"] = float(numeric.mean()) if numeric.notna().any() else None
    elif col_type == ColumnType.CATEGORY:
        stats["categories"] = non_null_str.value_counts().head(20).to_dict()

    return stats


def profile_spreadsheet(data: SpreadsheetData) -> SpreadsheetProfile:
    """
    Generate a comprehensive profile of the spreadsheet.

    Args:
        data: Loaded spreadsheet data

    Returns:
        SpreadsheetProfile with column profiles and overall stats
    """
    df = data.dataframe
    rows, cols = df.shape

    # Count empty rows (all values empty/NaN/missing-marker)
    empty_mask = df.map(is_missing_value).all(axis=1)
    empty_rows = int(empty_mask.sum())

    # Count duplicate rows (exact duplicates)
    duplicate_rows = int(df.duplicated().sum())

    # Total and empty cells
    total_cells = rows * cols
    empty_cells = int(df.map(is_missing_value).sum().sum())

    column_profiles = []
    for col_name in df.columns:
        series = df[col_name]
        null_count = int(series.map(is_missing_value).sum())
        null_pct = null_count / rows if rows > 0 else 0.0
        unique_count = int(series.nunique(dropna=False))

        # Sample values (non-null, non-empty, non-marker)
        non_empty = series[~series.map(is_missing_value)]
        sample_values = non_empty.head(5).tolist()

        inferred_type = _infer_column_type(series)
        stats = _compute_column_stats(series, inferred_type)

        column_profiles.append(
            ColumnProfile(
                name=str(col_name),
                dtype=str(series.dtype),
                inferred_type=inferred_type,
                null_count=null_count,
                null_percentage=null_pct,
                unique_count=unique_count,
                sample_values=sample_values,
                stats=stats,
            )
        )

    return SpreadsheetProfile(
        filename=data.filename,
        shape=(rows, cols),
        columns=column_profiles,
        sheet_count=data.sheet_count,
        empty_rows=empty_rows,
        duplicate_rows=duplicate_rows,
        total_cells=total_cells,
        empty_cells=empty_cells,
    )


def analyze_spreadsheet(
    data: SpreadsheetData, profile: SpreadsheetProfile | None = None
) -> AnalysisResult:
    """
    Analyze spreadsheet for data quality issues.

    Args:
        data: Loaded spreadsheet data
        profile: Optional pre-computed profile

    Returns:
        AnalysisResult with detected issues and suggested operations
    """
    if profile is None:
        profile = profile_spreadsheet(data)

    df = data.dataframe
    issues: dict[str, list[dict[str, Any]]] = {}
    suggested_ops = []

    # Empty rows (including missing-marker-only rows)
    empty_mask = df.map(is_missing_value).all(axis=1)
    empty_row_indices = df.index[empty_mask].tolist()
    if empty_row_indices:
        issues["empty_rows"] = [{"row": int(i) + 1} for i in empty_row_indices]
        suggested_ops.append("remove_empty_rows")

    # Duplicate rows (exact)
    dup_mask = df.duplicated(keep="first")
    dup_indices = df.index[dup_mask].tolist()
    if dup_indices:
        issues["duplicate_rows"] = [{"row": int(i) + 1} for i in dup_indices]
        suggested_ops.append("remove_duplicate_rows")

    # Phone columns get formatting normalization even without visible issues
    if any(c.inferred_type == ColumnType.PHONE for c in profile.columns):
        suggested_ops.append("normalize_phones")

    # Column-specific issues
    for col_profile in profile.columns:
        col_name = col_profile.name
        series = df[col_name]
        non_empty = series[~series.map(is_missing_value)]

        if len(non_empty) == 0:
            continue

        col_issues = []

        # Whitespace issues
        ws_mask = non_empty.astype(str).apply(lambda x: x != x.strip())
        ws_indices = non_empty.index[ws_mask].tolist()
        if ws_indices:
            col_issues.extend(
                [{"row": int(i) + 1, "issue": "leading_trailing_whitespace"} for i in ws_indices]
            )
            if "normalize_whitespace" not in suggested_ops:
                suggested_ops.append("normalize_whitespace")

        # Capitalization inconsistency (for text columns)
        if col_profile.inferred_type in (
            ColumnType.NAME,
            ColumnType.COMPANY,
            ColumnType.TEXT,
            ColumnType.CATEGORY,
        ):
            # Check if there are mixed case variations of same value
            normalized = non_empty.astype(str).str.strip().str.lower()
            value_groups = normalized.value_counts()
            inconsistent_values = value_groups[value_groups > 1].index.tolist()
            if inconsistent_values:
                for val in inconsistent_values[:10]:  # Limit examples
                    orig_indices = non_empty.index[normalized == val].tolist()
                    col_issues.extend(
                        [
                            {
                                "row": int(i) + 1,
                                "issue": "inconsistent_capitalization",
                                "values": non_empty.loc[i],
                            }
                            for i in orig_indices[:3]
                        ]
                    )
                if "normalize_capitalization" not in suggested_ops:
                    suggested_ops.append("normalize_capitalization")

        # Email validation
        if col_profile.inferred_type == ColumnType.EMAIL:
            invalid_mask = non_empty.astype(str).apply(lambda x: not EMAIL_PATTERN.match(x.strip()))
            invalid_indices = non_empty.index[invalid_mask].tolist()
            if invalid_indices:
                col_issues.extend(
                    [
                        {
                            "row": int(i) + 1,
                            "issue": "invalid_email",
                            "value": str(non_empty.loc[i]),
                        }
                        for i in invalid_indices
                    ]
                )
                if "validate_emails" not in suggested_ops:
                    suggested_ops.append("validate_emails")

            # Duplicate emails
            email_series = non_empty.astype(str).str.strip().str.lower()
            dup_email_mask = email_series.duplicated(keep="first")
            dup_email_indices = non_empty.index[dup_email_mask].tolist()
            if dup_email_indices:
                col_issues.extend(
                    [
                        {
                            "row": int(i) + 1,
                            "issue": "duplicate_email",
                            "value": str(non_empty.loc[i]),
                        }
                        for i in dup_email_indices
                    ]
                )
                if "remove_duplicate_emails" not in suggested_ops:
                    suggested_ops.append("remove_duplicate_emails")

        # Date parsing issues
        if col_profile.inferred_type == ColumnType.DATE:
            parsed = pd.to_datetime(non_empty.astype(str).str.strip(), errors="coerce")
            unparseable_mask = parsed.isna()
            unparseable_indices = non_empty.index[unparseable_mask].tolist()
            if unparseable_indices:
                col_issues.extend(
                    [
                        {
                            "row": int(i) + 1,
                            "issue": "unparseable_date",
                            "value": str(non_empty.loc[i]),
                        }
                        for i in unparseable_indices
                    ]
                )
                if "normalize_dates" not in suggested_ops:
                    suggested_ops.append("normalize_dates")

        if col_issues:
            issues[col_name] = col_issues

    return AnalysisResult(
        profile=profile,
        issues=issues,
        suggested_operations=suggested_ops,
    )

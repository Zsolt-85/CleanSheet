"""General value normalization."""

from __future__ import annotations

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel

# Text markers people use for "no value". Compared case-insensitively after
# stripping. Kept conservative: bare "na" is included because in contact/lead
# data it overwhelmingly means "not applicable" (and every conversion is
# logged in the report with the original value, so it's recoverable).
MISSING_TOKENS = frozenset(
    {
        "n/a",
        "na",
        "n.a.",
        "#n/a",
        "null",
        "nil",
        "none",
        "nan",
        "<na>",
        "-",
        "--",
    }
)


def is_missing_value(value: object) -> bool:
    """True for empty, null, or missing-marker values (N/A, NULL, -, ...)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    return text == "" or text.lower() in MISSING_TOKENS


def remove_empty_rows(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    rule_name: str = "remove_empty_rows",
) -> pd.DataFrame:
    """
    Remove completely empty rows.

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with empty rows removed
    """
    empty_mask = df.map(is_missing_value).all(axis=1)
    empty_indices = df.index[empty_mask].tolist()

    if not empty_indices:
        return df

    for idx in empty_indices:
        tracker.add_change(
            ChangeRecord(
                row_index=int(idx),
                column_name="*",
                original_value="<EMPTY ROW>",
                new_value="<REMOVED>",
                reason="Completely empty row removed",
                rule_name=rule_name,
                confidence=ConfidenceLevel.HIGH,
                applied=True,
            )
        )

    return df.drop(index=empty_indices).reset_index(drop=True)


def normalize_null_values(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    rule_name: str = "normalize_nulls",
    replacement: str = "",
) -> pd.DataFrame:
    """
    Normalize null/NaN values and missing-marker tokens (N/A, NULL, -, ...)
    to a consistent representation.

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking
        replacement: Value to replace nulls with

    Returns:
        DataFrame with normalized nulls
    """
    for col in df.columns:
        original_series = df[col].copy()

        for idx, value in original_series.items():
            if pd.isna(value):
                tracker.add_change(
                    ChangeRecord(
                        row_index=int(idx),
                        column_name=col,
                        original_value="<NULL>",
                        new_value=replacement,
                        reason="Null value normalized",
                        rule_name=rule_name,
                        confidence=ConfidenceLevel.HIGH,
                        applied=True,
                    )
                )
                df.at[idx, col] = replacement
            elif isinstance(value, str) and value.strip().lower() in MISSING_TOKENS:
                tracker.add_change(
                    ChangeRecord(
                        row_index=int(idx),
                        column_name=col,
                        original_value=value,
                        new_value=replacement,
                        reason=f"Missing-value marker {value.strip()!r} normalized to empty",
                        rule_name=rule_name,
                        confidence=ConfidenceLevel.HIGH,
                        applied=True,
                    )
                )
                df.at[idx, col] = replacement

    return df


# Country name -> ISO 3166-1 alpha-2. Exact full-value match only (after
# strip + lowercase); every conversion is logged with its original value.
COUNTRY_MAP = {
    "united states": "US",
    "usa": "US",
    "u.s.a.": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "italy": "IT",
    "italia": "IT",
    "spain": "ES",
    "espana": "ES",
    "españa": "ES",
    "canada": "CA",
    "australia": "AU",
    "japan": "JP",
    "china": "CN",
    "india": "IN",
    "brazil": "BR",
    "mexico": "MX",
    "netherlands": "NL",
    "holland": "NL",
    "belgium": "BE",
    "belgie": "BE",
    "belgique": "BE",
    "switzerland": "CH",
    "austria": "AT",
    "österreich": "AT",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "poland": "PL",
    "polska": "PL",
    "russia": "RU",
    "turkey": "TR",
    "türkiye": "TR",
    "israel": "IL",
    "uae": "AE",
    "united arab emirates": "AE",
    "singapore": "SG",
    "hong kong": "HK",
    "south korea": "KR",
    "korea": "KR",
    "taiwan": "TW",
    "new zealand": "NZ",
    "romania": "RO",
    "românia": "RO",
    "hungary": "HU",
    "magyarország": "HU",
    "bulgaria": "BG",
    "serbia": "RS",
    "srbija": "RS",
    "moldova": "MD",
    "republic of moldova": "MD",
    "ukraine": "UA",
    "croatia": "HR",
    "hrvatska": "HR",
    "greece": "GR",
    "ellada": "GR",
    "ireland": "IE",
    "portugal": "PT",
    "czechia": "CZ",
    "czech republic": "CZ",
    "slovakia": "SK",
    "slovenia": "SI",
}


def normalize_country_codes(
    df: pd.DataFrame,
    column: str,
    tracker: ChangeTracker,
    rule_name: str = "normalize_countries",
) -> pd.DataFrame:
    """
    Normalize country names to ISO 3166-1 alpha-2 codes.

    Args:
        df: Input DataFrame
        column: Column name with country codes
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with normalized country codes
    """
    if column not in df.columns:
        return df

    original_series = df[column].copy()

    for idx, value in original_series.items():
        if is_missing_value(value):
            continue

        original = str(value).strip()
        lower = original.lower()

        if lower in COUNTRY_MAP:
            normalized = COUNTRY_MAP[lower]
            if normalized != original:
                tracker.add_change(
                    ChangeRecord(
                        row_index=int(idx),
                        column_name=column,
                        original_value=original,
                        new_value=normalized,
                        reason="Country name normalized to ISO code",
                        rule_name=rule_name,
                        confidence=ConfidenceLevel.HIGH,
                        applied=True,
                    )
                )
                df.at[idx, column] = normalized

    return df


def normalize_all_countries(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    rule_name: str = "normalize_countries",
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Normalize country names in given columns, or auto-detect country
    columns (majority of values match known country names).

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking
        columns: Specific columns, or None to auto-detect
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with normalized country codes in auto-detected columns
    """
    if columns is None:
        columns = []
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().astype(str)
            sample = sample[~sample.map(is_missing_value)].head(30)
            if len(sample) == 0:
                continue
            hits = sample.apply(lambda x: x.strip().lower() in COUNTRY_MAP).sum()
            if hits / len(sample) > 0.5:
                columns.append(col)
    for col in columns:
        df = normalize_country_codes(df, col, tracker, rule_name)
    return df

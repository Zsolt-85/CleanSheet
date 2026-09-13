"""Phone number normalization and validation.

Deterministic and conservative:
- Cosmetic cleanup (separator/whitespace/00-prefix handling) is always safe.
- Country is never guessed: only an explicit leading + or 00 keeps an
  international prefix; local numbers stay prefix-less.
- Implausible lengths (fewer than 7 / more than 15 digits, per E.164) are
  flagged, never rewritten.
"""

from __future__ import annotations

import re

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel
from cleaning_engine.normalization import is_missing_value

PHONE_PATTERN = re.compile(r"^[\d\s\-\.\+\(\)/]{7,}$")

MIN_DIGITS = 7
MAX_DIGITS = 15


def _looks_like_phone_value(value: str) -> bool:
    """Loose screen: allowed chars and at least MIN_DIGITS digits."""
    if not bool(PHONE_PATTERN.match(value)):
        return False
    return len(re.sub(r"\D", "", value)) >= MIN_DIGITS


def normalize_phone(value: str) -> str:
    """Canonical form: optional leading + (from + or 00), then digits only."""
    if not isinstance(value, str):
        return "" if value is None else str(value)
    text = value.strip()
    international = text.startswith("+") or text.startswith("00")
    digits = re.sub(r"\D", "", text)
    if international:
        # "00" prefix and any trunk zeros collapse into a single leading +
        return "+" + digits.lstrip("0")
    # National format: keep the trunk prefix (e.g. leading 0) as-is
    return digits


def is_valid_phone(value: str) -> bool:
    """Plausible length check on the digit content (E.164 bounds)."""
    if not isinstance(value, str):
        return False
    digits = re.sub(r"\D", "", value.strip())
    return MIN_DIGITS <= len(digits) <= MAX_DIGITS


def normalize_phones_column(
    df: pd.DataFrame,
    column: str,
    tracker: ChangeTracker,
    rule_name: str = "normalize_phones",
    strict: bool = False,
) -> pd.DataFrame:
    """Normalize phone formatting in one column; flag implausible lengths.

    With strict=True (explicitly chosen phone columns, e.g. from the pipeline
    after profile screening), values that don't look like phones at all are
    flagged too. Auto-detected mixed columns run non-strict to avoid noise.
    """
    if column not in df.columns:
        return df

    original_series = df[column].copy()
    for idx, value in original_series.items():
        if is_missing_value(value):
            continue
        original = str(value)
        if not _looks_like_phone_value(original.strip()):
            if strict:
                tracker.add_change(
                    ChangeRecord(
                        row_index=int(idx),
                        column_name=column,
                        original_value=original,
                        new_value=f"INVALID: {original}",
                        reason="Does not look like a phone number",
                        rule_name="validate_phones",
                        confidence=ConfidenceLevel.HIGH,
                        applied=False,
                    )
                )
            continue
        if not is_valid_phone(original):
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=f"INVALID: {original}",
                    reason="Implausible phone number length",
                    rule_name="validate_phones",
                    confidence=ConfidenceLevel.HIGH,
                    applied=False,
                )
            )
            continue
        normalized = normalize_phone(original)
        if normalized != original:
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=column,
                    original_value=original,
                    new_value=normalized,
                    reason="Phone number formatting normalized",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.HIGH,
                    applied=True,
                )
            )
            df.at[idx, column] = normalized
    return df


def normalize_all_phones(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    rule_name: str = "normalize_phones",
    columns: list[str] | None = None,
    strict: bool = True,
) -> pd.DataFrame:
    """Normalize phones in given columns, or auto-detect phone-like columns.

    Explicit columns run strict (junk flagged); auto-detected ones don't, to
    avoid noise on mixed columns.
    """
    auto = columns is None
    if auto:
        columns = []
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().astype(str)
            sample = sample[~sample.map(is_missing_value)].head(30)
            if len(sample) == 0:
                continue
            hits = sample.apply(lambda x: _looks_like_phone_value(x.strip())).sum()
            if hits / len(sample) > 0.5:
                columns.append(col)
    for col in columns:
        df = normalize_phones_column(df, col, tracker, rule_name, strict=strict and not auto)
    return df

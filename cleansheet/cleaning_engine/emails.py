"""Email validation and normalization."""

from __future__ import annotations

import re

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Common email typos and their corrections
COMMON_TYPOS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmal.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outllok.com": "outlook.com",
    "icloud.com": "icloud.com",  # no typo, just for completeness
    "aol.com": "aol.com",
    "protonmail.com": "protonmail.com",
}


def is_valid_email(email: str) -> bool:
    """Check if email is valid."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    return bool(EMAIL_PATTERN.match(email))


def safe_normalize_email(email: str) -> str:
    """
    Normalize email address WITHOUT typo fixes (always safe):
    strip whitespace, lowercase, fix spaces around @ and dots.
    """
    if not email or not isinstance(email, str):
        return ""

    email = email.strip().lower()

    # Fix spaces around @
    email = re.sub(r"\s*@\s*", "@", email)

    # Fix spaces around dots in domain part
    if "@" in email:
        local, domain = email.split("@", 1)
        domain = re.sub(r"\s*\.\s*", ".", domain)
        email = f"{local}@{domain}"

    return email


def normalize_email(email: str) -> str:
    """
    Normalize email address:
    - Strip whitespace
    - Lowercase
    - Fix spaces around @ and dots
    - Fix common typos in domain
    """
    email = safe_normalize_email(email)
    if not email:
        return ""

    # Fix common domain typos
    for typo, correct in COMMON_TYPOS.items():
        if email.endswith("@" + typo):
            email = email[: -len(typo)] + correct
            break

    return email


def validate_emails(
    df: pd.DataFrame,
    email_column: str,
    tracker: ChangeTracker,
    rule_name: str = "validate_emails",
    auto_fix_typos: bool = True,
) -> pd.DataFrame:
    """
    Validate and optionally fix emails in a column.

    Args:
        df: Input DataFrame
        email_column: Name of email column
        tracker: ChangeTracker to record changes
        rule_name: Name of the rule for tracking
        auto_fix_typos: Whether to auto-fix common domain typos

    Returns:
        DataFrame with invalid emails marked (not removed)
    """
    if email_column not in df.columns:
        return df

    original_series = df[email_column].copy()

    for idx, value in original_series.items():
        if pd.isna(value) or str(value).strip() == "":
            continue

        original = str(value)
        normalized = normalize_email(original)

        if not is_valid_email(normalized):
            # Mark as invalid but keep original
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=email_column,
                    original_value=original,
                    new_value=f"INVALID: {original}",
                    reason="Invalid email format",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.HIGH,
                    applied=False,  # Don't auto-apply invalid marking
                )
            )
        elif normalized != original:
            typo_fixed = normalized != safe_normalize_email(original)
            if typo_fixed and not auto_fix_typos:
                # Conservative mode: suggest the typo fix, don't apply it
                tracker.add_change(
                    ChangeRecord(
                        row_index=int(idx),
                        column_name=email_column,
                        original_value=original,
                        new_value=normalized,
                        reason="Possible email typo - not auto-fixed (conservative mode)",
                        rule_name=rule_name,
                        confidence=ConfidenceLevel.MEDIUM,
                        applied=False,
                    )
                )
                continue
            # Valid but normalized (typo fixed or whitespace/case)
            tracker.add_change(
                ChangeRecord(
                    row_index=int(idx),
                    column_name=email_column,
                    original_value=original,
                    new_value=normalized,
                    reason="Email normalized (typo fix, whitespace, case)",
                    rule_name=rule_name,
                    confidence=ConfidenceLevel.HIGH
                    if original.lower() == normalized
                    else ConfidenceLevel.MEDIUM,
                    applied=True,
                )
            )
            df.at[idx, email_column] = normalized

    return df

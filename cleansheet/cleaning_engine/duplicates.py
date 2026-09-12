"""Duplicate detection and removal."""

from __future__ import annotations

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeRecord, ConfidenceLevel


def detect_duplicate_rows(df: pd.DataFrame, keep: str = "first") -> pd.Series:
    """
    Detect duplicate rows.

    Args:
        df: DataFrame to check
        keep: 'first', 'last', or False to mark all duplicates

    Returns:
        Boolean Series marking duplicate rows
    """
    return df.duplicated(keep=keep)


def remove_duplicate_rows(
    df: pd.DataFrame,
    tracker: ChangeTracker,
    keep: str = "first",
    rule_name: str = "remove_duplicate_rows",
) -> pd.DataFrame:
    """
    Remove exact duplicate rows.

    Args:
        df: Input DataFrame
        tracker: ChangeTracker to record changes
        keep: Which duplicate to keep ('first' or 'last')
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with duplicates removed
    """
    dup_mask = df.duplicated(keep=keep)
    dup_indices = df.index[dup_mask].tolist()

    if not dup_indices:
        return df

    # Record each removed row
    for idx in dup_indices:
        row_data = df.loc[idx].to_dict()
        tracker.add_change(
            ChangeRecord(
                row_index=int(idx),
                column_name="*",
                original_value=str(row_data),
                new_value="<REMOVED>",
                reason="Exact duplicate row removed",
                rule_name=rule_name,
                confidence=ConfidenceLevel.HIGH,
                applied=True,
            )
        )

    return df.drop(index=dup_indices).reset_index(drop=True)


def detect_duplicate_emails(df: pd.DataFrame, email_column: str, keep: str = "first") -> pd.Series:
    """
    Detect duplicate emails in a specific column (case-insensitive).

    Args:
        df: DataFrame to check
        email_column: Name of email column
        keep: 'first', 'last', or False

    Returns:
        Boolean Series marking duplicate emails
    """
    if email_column not in df.columns:
        return pd.Series(False, index=df.index)

    emails = df[email_column].astype(str).str.strip().str.lower()
    return emails.duplicated(keep=keep)


def remove_duplicate_emails(
    df: pd.DataFrame,
    email_column: str,
    tracker: ChangeTracker,
    keep: str = "first",
    rule_name: str = "remove_duplicate_emails",
) -> pd.DataFrame:
    """
    Remove rows with duplicate emails.

    Args:
        df: Input DataFrame
        email_column: Name of email column
        tracker: ChangeTracker to record changes
        keep: Which duplicate to keep
        rule_name: Name of the rule for tracking

    Returns:
        DataFrame with duplicate emails removed
    """
    if email_column not in df.columns:
        return df

    emails = df[email_column].astype(str).str.strip().str.lower()
    dup_mask = emails.duplicated(keep=keep)
    dup_indices = df.index[dup_mask].tolist()

    if not dup_indices:
        return df

    for idx in dup_indices:
        original_email = df.loc[idx, email_column]
        tracker.add_change(
            ChangeRecord(
                row_index=int(idx),
                column_name=email_column,
                original_value=original_email,
                new_value="<REMOVED>",
                reason="Duplicate email address removed",
                rule_name=rule_name,
                confidence=ConfidenceLevel.HIGH,
                applied=True,
            )
        )

    return df.drop(index=dup_indices).reset_index(drop=True)

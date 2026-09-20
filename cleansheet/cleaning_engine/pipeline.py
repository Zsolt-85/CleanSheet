"""Cleaning pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from cleaning_engine.capitalization import normalize_all_capitalization
from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.dates import normalize_all_dates
from cleaning_engine.duplicates import remove_duplicate_emails, remove_duplicate_rows
from cleaning_engine.emails import validate_emails
from cleaning_engine.exporter import export_both
from cleaning_engine.models import (
    AnalysisResult,
    SpreadsheetData,
    SpreadsheetProfile,
)
from cleaning_engine.normalization import (
    normalize_all_countries,
    normalize_null_values,
    remove_empty_rows,
)
from cleaning_engine.phones import normalize_all_phones
from cleaning_engine.profiler import analyze_spreadsheet, profile_spreadsheet
from cleaning_engine.whitespace import normalize_all_whitespace


@dataclass
class PipelineConfig:
    """Configuration for cleaning pipeline."""

    # Duplicate removal
    remove_duplicate_rows: bool = True
    remove_duplicate_emails: bool = True
    email_column: str | None = None  # Auto-detect if None

    # Whitespace
    normalize_whitespace: bool = True

    # Capitalization
    normalize_capitalization: bool = True
    capitalization_mode: str = "title"  # "title", "lower", "upper"

    # Dates
    normalize_dates: bool = True
    date_output_format: str = "%Y-%m-%d"
    dates_only_safe: bool = True

    # Email validation
    validate_emails: bool = True
    auto_fix_email_typos: bool = True

    # Phone normalization (safe formatting fixes on phone-type columns;
    # implausible lengths flagged, never rewritten)
    normalize_phones: bool = True

    # Country normalization (known country names to ISO codes, logged)
    normalize_countries: bool = True

    # Null handling
    normalize_nulls: bool = True
    null_replacement: str = ""

    # Empty rows
    remove_empty_rows: bool = True

    # Columns to process (None = all applicable)
    target_columns: list[str] | None = None
    skip_columns: list[str] = field(default_factory=list)


class CleaningPipeline:
    """
    Orchestrates the complete cleaning pipeline.

    Flow:
    1. Load spreadsheet
    2. Profile & analyze
    3. Apply cleaning operations (deterministic)
    4. Track all changes
    5. Export results
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.tracker = ChangeTracker()
        self.profile: SpreadsheetProfile | None = None
        self.analysis: AnalysisResult | None = None

    def run(self, data: SpreadsheetData) -> tuple[SpreadsheetData, ChangeTracker]:
        """
        Run the complete cleaning pipeline.

        Args:
            data: Input SpreadsheetData

        Returns:
            Tuple of (cleaned SpreadsheetData, ChangeTracker)
        """
        self.tracker.reset()

        # Step 1: Profile and analyze
        self.profile = profile_spreadsheet(data)
        self.analysis = analyze_spreadsheet(data, self.profile)

        # Auto-detect email column if not specified
        if self.config.email_column is None:
            for col_profile in self.profile.columns:
                if col_profile.inferred_type.value == "email":
                    self.config.email_column = col_profile.name
                    break

        # Step 2: Apply cleaning operations
        df = data.dataframe.copy()

        # Remove empty rows first (simplifies downstream)
        if self.config.remove_empty_rows:
            df = remove_empty_rows(df, self.tracker)

        # Normalize nulls
        if self.config.normalize_nulls:
            df = normalize_null_values(df, self.tracker, replacement=self.config.null_replacement)

        # Normalize whitespace (subsumes plain stripping: collapse +
        # strip). A separate strip step would steal its change records.
        if self.config.normalize_whitespace:
            df = normalize_all_whitespace(df, self.tracker, columns=self._get_target_columns(df))

        # Normalize capitalization (never on the email column:
        # title-casing corrupts addresses, and invalid emails would
        # keep the corruption since email fix-ups only apply to valid ones)
        if self.config.normalize_capitalization:
            cap_columns = self._get_target_columns(df)
            if cap_columns is not None and self.config.email_column:
                cap_columns = [c for c in cap_columns if c != self.config.email_column]
            df = normalize_all_capitalization(
                df,
                self.tracker,
                mode=self.config.capitalization_mode,
                columns=cap_columns,
            )

        # Normalize dates
        if self.config.normalize_dates:
            df = normalize_all_dates(
                df,
                self.tracker,
                output_format=self.config.date_output_format,
                only_safe=self.config.dates_only_safe,
                columns=self.config.target_columns,
            )

        # Normalize phones (profile-detected phone columns only: never
        # guess on numeric IDs or zips)
        if self.config.normalize_phones:
            df = normalize_all_phones(df, self.tracker, columns=self._phone_columns())

        # Normalize country names to ISO codes (auto-detected columns)
        if self.config.normalize_countries:
            df = normalize_all_countries(df, self.tracker)

        # Validate emails
        if self.config.validate_emails and self.config.email_column:
            df = validate_emails(
                df,
                self.config.email_column,
                self.tracker,
                auto_fix_typos=self.config.auto_fix_email_typos,
            )

        # Remove exact duplicate rows first (after normalization, so
        # case/whitespace variants that became identical are caught),
        # then remaining same-email-different-data rows.
        if self.config.remove_duplicate_rows:
            df = remove_duplicate_rows(df, self.tracker)

        # Remove duplicate emails
        if self.config.remove_duplicate_emails and self.config.email_column:
            df = remove_duplicate_emails(
                df,
                self.config.email_column,
                self.tracker,
            )

        # Create output SpreadsheetData
        cleaned_data = SpreadsheetData(
            dataframe=df,
            filename=data.filename,
            file_type=data.file_type,
            sheet_name=data.sheet_name,
            sheet_count=data.sheet_count,
        )

        return cleaned_data, self.tracker

    def _get_target_columns(self, df: pd.DataFrame) -> list[str] | None:
        """Get columns to process based on config."""
        if self.config.target_columns:
            return [
                c
                for c in self.config.target_columns
                if c in df.columns and c not in self.config.skip_columns
            ]
        return [c for c in df.columns if c not in self.config.skip_columns]

    def _phone_columns(self) -> list[str]:
        """Profile-detected phone columns (never guess on numeric IDs)."""
        if self.profile is None:
            return []
        return [
            c.name
            for c in self.profile.columns
            if c.inferred_type.value == "phone" and c.name not in self.config.skip_columns
        ]

    def run_and_export(
        self,
        data: SpreadsheetData,
        cleaned_output: str | Path,
        report_output: str | Path,
    ) -> tuple[Path, Path]:
        """
        Run pipeline and export results.

        Returns:
            Tuple of (cleaned_file_path, report_file_path)
        """
        cleaned_data, tracker = self.run(data)
        return export_both(cleaned_data, tracker, cleaned_output, report_output)


def create_default_pipeline() -> CleaningPipeline:
    """Create a pipeline with default configuration."""
    return CleaningPipeline(PipelineConfig())


def create_conservative_pipeline() -> CleaningPipeline:
    """Create a pipeline with conservative settings (less aggressive)."""
    return CleaningPipeline(
        PipelineConfig(
            remove_duplicate_rows=True,
            remove_duplicate_emails=True,
            normalize_whitespace=True,
            normalize_capitalization=False,  # Disabled by default
            normalize_dates=True,
            dates_only_safe=True,
            validate_emails=True,
            auto_fix_email_typos=False,  # Don't auto-fix typos
            normalize_nulls=True,
            remove_empty_rows=True,
        )
    )


def create_aggressive_pipeline() -> CleaningPipeline:
    """Create a pipeline with aggressive settings."""
    return CleaningPipeline(
        PipelineConfig(
            remove_duplicate_rows=True,
            remove_duplicate_emails=True,
            normalize_whitespace=True,
            normalize_capitalization=True,
            capitalization_mode="title",
            normalize_dates=True,
            dates_only_safe=False,
            validate_emails=True,
            auto_fix_email_typos=True,
            normalize_nulls=True,
            remove_empty_rows=True,
        )
    )

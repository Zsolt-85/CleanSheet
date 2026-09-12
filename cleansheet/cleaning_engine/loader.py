"""Spreadsheet loading utilities."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pandas as pd

from cleaning_engine.models import SpreadsheetData

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = 25
MAX_ROWS = 50_000
MAX_COLUMNS = 200


class SpreadsheetLoadError(Exception):
    """Raised when spreadsheet loading fails."""

    pass


def validate_file(file_path: Path) -> None:
    """Validate file before loading."""
    if not file_path.exists():
        raise SpreadsheetLoadError(f"File not found: {file_path}")

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SpreadsheetLoadError(
            f"Unsupported file type: {file_path.suffix}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise SpreadsheetLoadError(
            f"File too large: {file_size_mb:.1f}MB (max: {MAX_FILE_SIZE_MB}MB)"
        )


def detect_delimiter(path: Path) -> str:
    """Detect a CSV delimiter (comma, semicolon, tab, pipe).

    European Excel exports commonly use semicolons. Falls back to comma
    when detection fails, preserving previous behavior.
    """
    try:
        sample = path.read_bytes()[:8192].decode("utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return ","
    if "\n" not in sample and "\r" not in sample:
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except csv.Error:
        return ","


def load_spreadsheet(file_path: str | Path, sheet_name: str | int | None = 0) -> SpreadsheetData:
    """
    Load a spreadsheet file (CSV or Excel) into a DataFrame.

    Args:
        file_path: Path to the spreadsheet file
        sheet_name: Sheet name or index for Excel files (default: first sheet)

    Returns:
        SpreadsheetData with DataFrame and metadata

    Raises:
        SpreadsheetLoadError: If file cannot be loaded or validation fails
    """
    path = Path(file_path)
    validate_file(path)

    file_type = path.suffix.lower().lstrip(".")
    actual_sheet_name = None

    try:
        if file_type == "csv":
            delimiter = detect_delimiter(path)
            # Try different encodings
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    df = pd.read_csv(
                        path,
                        encoding=encoding,
                        sep=delimiter,
                        dtype=str,
                        keep_default_na=False,
                    )
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise SpreadsheetLoadError("Unable to decode CSV with supported encodings")

        elif file_type in ("xlsx", "xls"):
            actual_sheet_name = sheet_name
            df = pd.read_excel(
                path, sheet_name=sheet_name, dtype=str, keep_default_na=False, engine="openpyxl"
            )
            if isinstance(df, dict):
                # Multiple sheets returned - use first
                first_sheet = next(iter(df))
                df = df[first_sheet]
                actual_sheet_name = first_sheet

        else:
            raise SpreadsheetLoadError(f"Unsupported file type: {file_type}")

    except SpreadsheetLoadError:
        raise
    except pd.errors.EmptyDataError:
        raise SpreadsheetLoadError("File is empty")
    except pd.errors.ParserError as e:
        raise SpreadsheetLoadError(f"Failed to parse file: {e}")
    except Exception as e:
        raise SpreadsheetLoadError(f"Unexpected error loading file: {e}")

    # Validate dimensions
    rows, cols = df.shape
    if rows > MAX_ROWS:
        raise SpreadsheetLoadError(f"Too many rows: {rows} (max: {MAX_ROWS})")
    if cols > MAX_COLUMNS:
        raise SpreadsheetLoadError(f"Too many columns: {cols} (max: {MAX_COLUMNS})")

    # Normalize column names (strip whitespace)
    df.columns = df.columns.astype(str).str.strip()

    return SpreadsheetData(
        dataframe=df,
        filename=path.name,
        file_type=file_type,
        sheet_name=str(actual_sheet_name) if actual_sheet_name is not None else None,
    )


def safe_filename(filename: str) -> str:
    """Sanitize an uploader-provided filename: basename only, no path tricks,
    reasonable length, fallback when empty."""
    name = Path(filename or "").name.strip().replace("\\", "_").replace("/", "_")
    if not name or name in (".", ".."):
        return "upload.csv"
    return name[:100]


def load_spreadsheet_from_bytes(
    content: bytes,
    filename: str,
    sheet_name: str | int | None = 0,
) -> SpreadsheetData:
    """Load spreadsheet from bytes (for web uploads).

    The original filename is preserved on the result (sanitized) — callers
    use it for download names and reporting.
    """
    filename = safe_filename(filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise SpreadsheetLoadError(f"Unsupported file type: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        data = load_spreadsheet(tmp_path, sheet_name)
    finally:
        tmp_path.unlink(missing_ok=True)
    data.filename = filename
    return data

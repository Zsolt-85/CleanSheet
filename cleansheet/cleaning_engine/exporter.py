"""Export cleaned spreadsheet and change report."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cleaning_engine.change_tracker import ChangeTracker
from cleaning_engine.models import ChangeReport, SpreadsheetData


def export_cleaned(
    data: SpreadsheetData,
    output_path: str | Path,
    index: bool = False,
) -> Path:
    """
    Export cleaned spreadsheet to file.

    Args:
        data: SpreadsheetData with cleaned DataFrame
        output_path: Output file path
        index: Whether to include row index

    Returns:
        Path to exported file
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".csv":
        data.dataframe.to_csv(path, index=index, encoding="utf-8")
    elif path.suffix.lower() in (".xlsx", ".xls"):
        data.dataframe.to_excel(path, index=index, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported output format: {path.suffix}")

    return path


def visualize_whitespace(value: object) -> object:
    """Make invisible whitespace visible for the human-readable report.

    Leading/trailing spaces become middle dots, tabs become arrows,
    newlines become return symbols — so a change like "Vlad " -> "Vlad"
    is actually visible in the exported sheet. Non-string values pass
    through untouched.
    """
    if not isinstance(value, str):
        return value
    out: list[str] = []
    n = len(value)
    for i, ch in enumerate(value):
        if ch == " " and (i == 0 or i == n - 1 or value[i - 1] == " " or value[i + 1] == " "):
            # leading, trailing, or part of a multi-space run
            out.append("·")
        elif ch == " ":
            out.append(ch)
        elif ch == "\t":
            out.append("→")
        elif ch == "\n":
            out.append("↵")
        elif ch == "\r":
            out.append("␍")
        else:
            out.append(ch)
    # trailing single space (loop above only catches it via i == n-1 — covered)
    return "".join(out)


def export_report(
    report: ChangeReport | ChangeTracker,
    output_path: str | Path,
    index: bool = False,
    source: SpreadsheetData | None = None,
) -> Path:
    """
    Export change report to Excel file with multiple sheets.

    Args:
        report: ChangeReport or ChangeTracker
        output_path: Output file path (.xlsx)
        index: Whether to include row index
        source: Optional source spreadsheet; when it holds more than one
            sheet, the Summary sheet records the sheet count and the name
            of the cleaned sheet (loud multi-sheet handling, never silent)

    Returns:
        Path to exported file
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(report, ChangeTracker):
        report = report.to_report()

    changes_df = report.to_dataframe()
    # Human-readable sheet only: expose invisible whitespace. The raw values
    # stay untouched in to_dataframe() for programmatic use.
    for col in ("original", "new"):
        if col in changes_df.columns:
            changes_df[col] = changes_df[col].map(visualize_whitespace)
    metrics = ["Total Changes", "Applied", "Pending Review", "Processing Time (ms)"]
    values: list[object] = [
        len(report.changes),
        len(report.get_applied_changes())
        if hasattr(report, "get_applied_changes")
        else sum(1 for c in report.changes if c.applied),
        len(report.get_pending_changes())
        if hasattr(report, "get_pending_changes")
        else sum(1 for c in report.changes if not c.applied),
        f"{report.processing_time_ms:.1f}",
    ]
    if source is not None and source.sheet_count > 1:
        metrics += ["Sheets in file", "Sheet cleaned"]
        values += [source.sheet_count, source.sheet_name or "—"]
    summary_df = pd.DataFrame({"Metric": metrics, "Value": values})

    # Rule summary
    rule_summary = []
    for rule, count in sorted(report.summary.items(), key=lambda x: -x[1]):
        rule_summary.append({"Rule": rule, "Count": count})
    rule_df = (
        pd.DataFrame(rule_summary) if rule_summary else pd.DataFrame(columns=["Rule", "Count"])
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        changes_df.to_excel(writer, sheet_name="Changes", index=index)
        summary_df.to_excel(writer, sheet_name="Summary", index=index)
        rule_df.to_excel(writer, sheet_name="By Rule", index=index)

    return path


def export_both(
    data: SpreadsheetData,
    report: ChangeReport | ChangeTracker,
    cleaned_path: str | Path,
    report_path: str | Path,
) -> tuple[Path, Path]:
    """
    Export both cleaned spreadsheet and change report.

    Returns:
        Tuple of (cleaned_path, report_path)
    """
    cleaned = export_cleaned(data, cleaned_path)
    report_file = export_report(report, report_path)
    return cleaned, report_file

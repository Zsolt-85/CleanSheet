"""Core data models for the cleaning engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class ColumnType(str, Enum):
    """Detected column types."""

    UNKNOWN = "unknown"
    EMAIL = "email"
    PHONE = "phone"
    DATE = "date"
    NAME = "name"
    COMPANY = "company"
    ADDRESS = "address"
    CATEGORY = "category"
    NUMERIC = "numeric"
    TEXT = "text"


class ConfidenceLevel(str, Enum):
    """Confidence levels for transformations."""

    HIGH = "high"  # >= 95% - auto apply
    MEDIUM = "medium"  # 70-94% - ask user
    LOW = "low"  # < 70% - don't apply


@dataclass
class SpreadsheetData:
    """Loaded spreadsheet with metadata."""

    dataframe: pd.DataFrame
    filename: str
    file_type: str  # "csv" or "xlsx"
    sheet_name: str | None = None
    original_shape: tuple[int, int] = field(init=False)

    def __post_init__(self) -> None:
        self.original_shape = self.dataframe.shape


@dataclass
class ColumnProfile:
    """Profile of a single column."""

    name: str
    dtype: str
    inferred_type: ColumnType = ColumnType.UNKNOWN
    null_count: int = 0
    null_percentage: float = 0.0
    unique_count: int = 0
    sample_values: list[Any] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpreadsheetProfile:
    """Complete spreadsheet profile."""

    filename: str
    shape: tuple[int, int]
    columns: list[ColumnProfile]
    empty_rows: int = 0
    duplicate_rows: int = 0
    total_cells: int = 0
    empty_cells: int = 0


@dataclass
class ChangeRecord:
    """Record of a single change made during cleaning."""

    row_index: int
    column_name: str
    original_value: Any
    new_value: Any
    reason: str
    rule_name: str
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    applied: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row_index + 1,  # 1-indexed for user display
            "column": self.column_name,
            "original": str(self.original_value) if self.original_value is not None else "",
            "new": str(self.new_value) if self.new_value is not None else "",
            "reason": self.reason,
            "rule": self.rule_name,
            "confidence": self.confidence.value,
            "applied": self.applied,
        }


@dataclass
class ChangeReport:
    """Complete change report for a cleaning operation."""

    changes: list[ChangeRecord] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    processing_time_ms: float = 0.0

    def add_change(self, change: ChangeRecord) -> None:
        self.changes.append(change)
        self.summary[change.rule_name] = self.summary.get(change.rule_name, 0) + 1

    def to_dataframe(self) -> pd.DataFrame:
        if not self.changes:
            return pd.DataFrame(
                columns=[
                    "row",
                    "column",
                    "original",
                    "new",
                    "reason",
                    "rule",
                    "confidence",
                    "applied",
                ]
            )
        return pd.DataFrame([c.to_dict() for c in self.changes])

    def get_summary_text(self) -> str:
        lines = [f"Total changes: {len(self.changes)}"]
        for rule, count in sorted(self.summary.items()):
            lines.append(f"  {rule}: {count}")
        return "\n".join(lines)


@dataclass
class AnalysisResult:
    """Result of spreadsheet analysis."""

    profile: SpreadsheetProfile
    issues: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    suggested_operations: list[str] = field(default_factory=list)

    def get_issue_count(self, issue_type: str) -> int:
        return len(self.issues.get(issue_type, []))

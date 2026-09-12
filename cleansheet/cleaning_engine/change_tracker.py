"""Change tracking system."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from cleaning_engine.models import ChangeRecord, ChangeReport, ConfidenceLevel


@dataclass
class ChangeTracker:
    """
    Tracks all changes made during cleaning pipeline.

    Provides:
    - Per-cell change records with reason, rule, confidence
    - Summary statistics
    - Export to DataFrame/Excel
    """

    changes: list[ChangeRecord] = field(default_factory=list)
    start_time: float = field(default_factory=time.perf_counter)
    rule_counts: dict[str, int] = field(default_factory=dict)
    confidence_counts: dict[ConfidenceLevel, int] = field(default_factory=dict)

    def add_change(self, change: ChangeRecord) -> None:
        """Add a change record."""
        self.changes.append(change)
        self.rule_counts[change.rule_name] = self.rule_counts.get(change.rule_name, 0) + 1
        self.confidence_counts[change.confidence] = (
            self.confidence_counts.get(change.confidence, 0) + 1
        )

    def get_changes_for_column(self, column: str) -> list[ChangeRecord]:
        """Get all changes for a specific column."""
        return [c for c in self.changes if c.column_name == column]

    def get_changes_for_row(self, row_index: int) -> list[ChangeRecord]:
        """Get all changes for a specific row."""
        return [c for c in self.changes if c.row_index == row_index]

    def get_changes_by_rule(self, rule_name: str) -> list[ChangeRecord]:
        """Get all changes by rule name."""
        return [c for c in self.changes if c.rule_name == rule_name]

    def get_changes_by_confidence(self, confidence: ConfidenceLevel) -> list[ChangeRecord]:
        """Get all changes by confidence level."""
        return [c for c in self.changes if c.confidence == confidence]

    def get_applied_changes(self) -> list[ChangeRecord]:
        """Get only applied changes."""
        return [c for c in self.changes if c.applied]

    def get_pending_changes(self) -> list[ChangeRecord]:
        """Get only pending (not applied) changes."""
        return [c for c in self.changes if not c.applied]

    def to_report(self) -> ChangeReport:
        """Generate a ChangeReport from tracked changes."""
        processing_time_ms = (time.perf_counter() - self.start_time) * 1000
        return ChangeReport(
            changes=self.changes.copy(),
            summary=self.rule_counts.copy(),
            processing_time_ms=processing_time_ms,
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Export changes as DataFrame."""
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
        """Get human-readable summary."""
        lines = [
            "CleanSheet Change Report",
            "=" * 40,
            f"Total changes: {len(self.changes)}",
            f"Applied: {len(self.get_applied_changes())}",
            f"Pending review: {len(self.get_pending_changes())}",
            f"Processing time: {(time.perf_counter() - self.start_time) * 1000:.1f}ms",
            "",
            "By rule:",
        ]
        for rule, count in sorted(self.rule_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {rule}: {count}")

        lines.append("")
        lines.append("By confidence:")
        for conf in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW]:
            count = self.confidence_counts.get(conf, 0)
            if count > 0:
                lines.append(f"  {conf.value}: {count}")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset tracker for new cleaning run."""
        self.changes.clear()
        self.rule_counts.clear()
        self.confidence_counts.clear()
        self.start_time = time.perf_counter()

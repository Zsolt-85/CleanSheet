"""CleanSheet - Automated spreadsheet cleaning engine."""

from cleaning_engine.change_tracker import ChangeRecord, ChangeReport, ChangeTracker
from cleaning_engine.exporter import export_both, export_cleaned, export_report
from cleaning_engine.loader import SpreadsheetData, load_spreadsheet, load_spreadsheet_from_bytes
from cleaning_engine.models import ColumnType, ConfidenceLevel
from cleaning_engine.modes import (
    GUARANTEES,
    GUARANTEES_RO,
    MODE_COMPARISON,
    MODE_COMPARISON_RO,
    MODE_IDS,
    MODES,
    MODES_RO,
    build_pipeline,
    get_modes_content,
)
from cleaning_engine.pipeline import (
    CleaningPipeline,
    PipelineConfig,
    create_aggressive_pipeline,
    create_conservative_pipeline,
    create_default_pipeline,
)
from cleaning_engine.profiler import (
    AnalysisResult,
    SpreadsheetProfile,
    analyze_spreadsheet,
    profile_spreadsheet,
)

__version__ = "0.1.0"
__all__ = [
    "AnalysisResult",
    "ChangeRecord",
    "ChangeReport",
    "ChangeTracker",
    "CleaningPipeline",
    "GUARANTEES",
    "GUARANTEES_RO",
    "MODE_COMPARISON",
    "MODE_COMPARISON_RO",
    "MODE_IDS",
    "MODES",
    "MODES_RO",
    "PipelineConfig",
    "build_pipeline",
    "get_modes_content",
    "SpreadsheetData",
    "SpreadsheetProfile",
    "analyze_spreadsheet",
    "create_aggressive_pipeline",
    "create_conservative_pipeline",
    "create_default_pipeline",
    "export_both",
    "export_cleaned",
    "export_report",
    "load_spreadsheet",
    "load_spreadsheet_from_bytes",
    "profile_spreadsheet",
]

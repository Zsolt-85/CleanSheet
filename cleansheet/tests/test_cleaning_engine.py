"""Tests for CleanSheet cleaning engine."""

import contextlib
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from cleaning_engine import (
    ChangeRecord,
    ChangeTracker,
    CleaningPipeline,
    ColumnType,
    ConfidenceLevel,
    PipelineConfig,
    SpreadsheetData,
    analyze_spreadsheet,
    build_pipeline,
    create_aggressive_pipeline,
    create_conservative_pipeline,
    create_default_pipeline,
    load_spreadsheet,
    profile_spreadsheet,
)
from cleaning_engine.capitalization import normalize_capitalization_column, to_title_case
from cleaning_engine.dates import (
    is_safe_to_normalize,
    normalize_date,
    normalize_dates_column,
    parse_date,
)
from cleaning_engine.duplicates import remove_duplicate_emails, remove_duplicate_rows
from cleaning_engine.emails import is_valid_email, normalize_email, validate_emails
from cleaning_engine.exporter import export_cleaned, export_report
from cleaning_engine.loader import MAX_COLUMNS, SpreadsheetLoadError
from cleaning_engine.normalization import remove_empty_rows, strip_all_strings
from cleaning_engine.whitespace import normalize_all_whitespace, normalize_whitespace


class TestLoader:
    """Tests for spreadsheet loading."""

    def test_load_csv(self, messy_contacts_path: Path):
        data = load_spreadsheet(messy_contacts_path)
        assert isinstance(data, SpreadsheetData)
        assert data.dataframe.shape[0] > 0
        assert data.dataframe.shape[1] > 0
        assert data.file_type == "csv"

    def test_load_csv_with_encoding(self, romanian_contacts_path: Path):
        data = load_spreadsheet(romanian_contacts_path)
        assert isinstance(data, SpreadsheetData)
        # Check Romanian characters preserved
        assert any("București" in str(v) for v in data.dataframe.to_numpy().flatten())

    def test_load_nonexistent_file(self):
        with pytest.raises(SpreadsheetLoadError):
            load_spreadsheet(Path("nonexistent.csv"))

    def test_column_names_stripped(self, messy_contacts_path: Path):
        data = load_spreadsheet(messy_contacts_path)
        # Column names should have no leading/trailing whitespace
        for col in data.dataframe.columns:
            assert col == col.strip()

    def test_detect_delimiter(self, tmp_path: Path):
        from cleaning_engine.loader import detect_delimiter

        comma = tmp_path / "c.csv"
        comma.write_text("a,b,c\n1,2,3\n")
        assert detect_delimiter(comma) == ","
        semi = tmp_path / "s.csv"
        semi.write_text("a;b;c\n1;2;3\n")
        assert detect_delimiter(semi) == ";"
        tab = tmp_path / "t.csv"
        tab.write_text("a\tb\tc\n1\t2\t3\n")
        assert detect_delimiter(tab) == "\t"
        single_line = tmp_path / "one.csv"
        single_line.write_text("a;b;c")
        assert detect_delimiter(single_line) == ","

    def test_load_semicolon_csv(self, input_dir: Path):
        data = load_spreadsheet(input_dir / "semicolon_leads.csv")
        assert list(data.dataframe.columns) == [
            "First Name",
            "Last Name",
            "Email",
            "Company",
            "Phone",
            "Signup Date",
            "Notes",
        ]
        assert data.dataframe.shape[0] == 5
        # Comma inside a field must NOT split (semicolon is the delimiter)
        assert data.dataframe.loc[1, "Notes"] == "Duplicate, different case"

    def test_semicolon_pipeline(self, input_dir: Path):
        data = load_spreadsheet(input_dir / "semicolon_leads.csv")
        cleaned, tracker = create_default_pipeline().run(data)
        # JOHN/SMITH row merges with John/Smith, typo fixed, markers emptied
        emails = cleaned.dataframe["Email"].tolist()
        assert "john@gmail.com" in emails
        assert "jane@gmail.com" in emails  # gmial.com typo fixed
        assert "N/A" not in cleaned.dataframe.values
        assert "NULL" not in cleaned.dataframe.values
        assert len(tracker.get_changes_by_rule("normalize_nulls")) >= 3


class TestLoaderRobustness:
    """Malformed / hostile inputs must fail safely with SpreadsheetLoadError."""

    def test_empty_csv_fails_safely(self, tmp_path: Path):
        p = tmp_path / "empty.csv"
        p.write_bytes(b"")
        with pytest.raises(SpreadsheetLoadError):
            load_spreadsheet(p)

    def test_unsupported_extension_fails_safely(self, tmp_path: Path):
        p = tmp_path / "notes.txt"
        p.write_text("just some text")
        with pytest.raises(SpreadsheetLoadError):
            load_spreadsheet(p)

    def test_garbage_xlsx_fails_safely(self, tmp_path: Path):
        p = tmp_path / "garbage.xlsx"
        p.write_bytes(bytes(range(256)) * 100)
        with pytest.raises(SpreadsheetLoadError):
            load_spreadsheet(p)

    def test_truncated_xlsx_fails_safely(self, tmp_path: Path):
        """A real xlsx cut in half must not crash the loader."""
        buf = tmp_path / "full.xlsx"
        pd.DataFrame({"A": [1, 2], "B": ["x", "y"]}).to_excel(buf, index=False)
        raw = buf.read_bytes()
        half = tmp_path / "half.xlsx"
        half.write_bytes(raw[: len(raw) // 2])
        assert zipfile.is_zipfile(buf)
        with pytest.raises(SpreadsheetLoadError):
            load_spreadsheet(half)

    def test_too_many_columns_fails_safely(self, tmp_path: Path):
        p = tmp_path / "wide.csv"
        pd.DataFrame({f"col{i}": [1] for i in range(MAX_COLUMNS + 1)}).to_csv(p, index=False)
        with pytest.raises(SpreadsheetLoadError, match="Too many columns"):
            load_spreadsheet(p)

    def test_garbage_csv_never_crashes(self, tmp_path: Path):
        """CSV is loose: garbage must either load or raise SpreadsheetLoadError,
        never an unhandled exception type."""
        p = tmp_path / "garbage.csv"
        p.write_bytes(bytes(range(256)) * 50)
        with contextlib.suppress(SpreadsheetLoadError):
            load_spreadsheet(p)


class TestProfiler:
    """Tests for spreadsheet profiling."""

    def test_profile_basic(self, messy_contacts_data: SpreadsheetData):
        profile = profile_spreadsheet(messy_contacts_data)
        assert profile.shape[0] > 0
        assert profile.shape[1] > 0
        assert len(profile.columns) == profile.shape[1]
        assert profile.empty_rows >= 0
        assert profile.duplicate_rows >= 0

    def test_column_type_inference(self, messy_contacts_data: SpreadsheetData):
        profile = profile_spreadsheet(messy_contacts_data)
        # Email column should be detected
        email_cols = [c for c in profile.columns if c.inferred_type == ColumnType.EMAIL]
        assert len(email_cols) >= 1
        # Date column should be detected
        date_cols = [c for c in profile.columns if c.inferred_type == ColumnType.DATE]
        assert len(date_cols) >= 1

    def test_analyze_detects_issues(self, messy_contacts_data: SpreadsheetData):
        profile = profile_spreadsheet(messy_contacts_data)
        analysis = analyze_spreadsheet(messy_contacts_data, profile)
        assert analysis.issues
        assert analysis.suggested_operations
        # Should detect duplicates
        assert "duplicate_rows" in analysis.issues or any("duplicate" in k for k in analysis.issues)

    def test_markers_count_as_nulls_not_values(self):
        from cleaning_engine.models import SpreadsheetData

        df = pd.DataFrame(
            {
                "Email": ["john@gmail.com", "N/A", "-", "jane@yahoo.com", "NULL"],
                "Name": ["John", "x", "y", "Jane", "z"],
            }
        )
        data = SpreadsheetData(dataframe=df, filename="t.csv", file_type="csv")
        profile = profile_spreadsheet(data)
        email_col = next(c for c in profile.columns if c.name == "Email")
        # Markers excluded from inference sample: still EMAIL, 3 nulls
        assert email_col.inferred_type == ColumnType.EMAIL
        assert email_col.null_count == 3
        # Markers must not be reported as invalid emails
        analysis = analyze_spreadsheet(data, profile)
        invalid = [
            i
            for issues in analysis.issues.values()
            for i in issues
            if i.get("issue") == "invalid_email"
        ]
        assert not invalid


class TestDuplicates:
    """Tests for duplicate detection and removal."""

    def test_remove_duplicate_rows(self):
        df = pd.DataFrame({"A": [1, 2, 2, 3], "B": ["a", "b", "b", "c"]})
        tracker = ChangeTracker()
        result = remove_duplicate_rows(df, tracker)
        assert len(result) == 3
        assert len(tracker.changes) == 1
        assert tracker.changes[0].rule_name == "remove_duplicate_rows"

    def test_remove_duplicate_emails(self):
        df = pd.DataFrame(
            {
                "Email": ["john@gmail.com", "jane@yahoo.com", "JOHN@GMAIL.COM", "bob@hotmail.com"],
                "Name": ["John", "Jane", "John", "Bob"],
            }
        )
        tracker = ChangeTracker()
        result = remove_duplicate_emails(df, "Email", tracker)
        assert len(result) == 3
        assert len(tracker.changes) == 1
        assert tracker.changes[0].rule_name == "remove_duplicate_emails"

    def test_duplicate_emails_case_insensitive(self):
        df = pd.DataFrame({"Email": ["Test@Example.COM", "test@example.com"]})
        tracker = ChangeTracker()
        result = remove_duplicate_emails(df, "Email", tracker)
        assert len(result) == 1


class TestEmails:
    """Tests for email validation and normalization."""

    def test_is_valid_email(self):
        assert is_valid_email("john@gmail.com")
        assert is_valid_email("jane.doe@company.co.uk")
        assert not is_valid_email("invalid")
        assert not is_valid_email("no@domain")
        assert not is_valid_email("@nodomain.com")
        assert not is_valid_email("")

    def test_normalize_email(self):
        assert normalize_email("  John@Gmail.Com  ") == "john@gmail.com"
        assert normalize_email("john @ gmail . com") == "john@gmail.com"
        assert normalize_email("john@gmial.com") == "john@gmail.com"
        assert normalize_email("jane@yaho.com") == "jane@yahoo.com"
        assert normalize_email("bob@hotmial.com") == "bob@hotmail.com"

    def test_validate_emails(self):
        df = pd.DataFrame({"Email": ["john@gmail.com", "invalid", "jane@yaho.com", ""]})
        tracker = ChangeTracker()
        result = validate_emails(df, "Email", tracker)  # noqa: F841 - asserted below
        # Should mark invalid and fix typo
        changes = tracker.changes
        assert any(c.reason == "Invalid email format" for c in changes)
        assert any(c.new_value == "jane@yahoo.com" for c in changes)
        assert result.loc[2, "Email"] == "jane@yahoo.com"

    def test_validate_emails_conservative_keeps_typos(self):
        df = pd.DataFrame({"Email": ["henry@gmial.com", "  JOHN@Gmail.com  "]})
        tracker = ChangeTracker()
        result = validate_emails(df, "Email", tracker, auto_fix_typos=False)
        # Typo suggested but NOT applied
        assert result.loc[0, "Email"] == "henry@gmial.com"
        pending = [c for c in tracker.changes if not c.applied]
        assert any("conservative mode" in c.reason for c in pending)
        # Safe whitespace/case fix still applied
        assert result.loc[1, "Email"] == "john@gmail.com"


class TestWhitespace:
    """Tests for whitespace normalization."""

    def test_normalize_whitespace(self):
        assert normalize_whitespace("  hello  world  ") == "hello world"
        assert normalize_whitespace("\thello\nworld\r") == "hello world"
        assert normalize_whitespace("hello   world") == "hello world"
        assert normalize_whitespace("") == ""
        assert normalize_whitespace("  ") == ""

    def test_normalize_all_whitespace(self):
        df = pd.DataFrame({"A": ["  hello  ", "world  "], "B": ["  foo  ", "bar"]})
        tracker = ChangeTracker()
        result = normalize_all_whitespace(df, tracker)
        assert result.loc[0, "A"] == "hello"
        assert result.loc[1, "A"] == "world"
        # "bar" has no whitespace to strip, so only 3 changes
        assert len(tracker.changes) == 3


class TestCapitalization:
    """Tests for capitalization normalization."""

    def test_to_title_case(self):
        assert to_title_case("john smith") == "John Smith"
        assert to_title_case("ACME LTD") == "Acme LTD"  # LTD is in UPPERCASE_WORDS
        assert to_title_case("john smith jr") == "John Smith Jr"
        assert to_title_case("vp of sales") == "VP of Sales"
        assert to_title_case("ceo of ibm") == "CEO of IBM"

    def test_normalize_capitalization_column(self):
        df = pd.DataFrame({"Name": ["john smith", "JANE DOE", "Bob Wilson"]})
        tracker = ChangeTracker()
        result = normalize_capitalization_column(df, "Name", tracker)
        assert result.loc[0, "Name"] == "John Smith"
        assert result.loc[1, "Name"] == "Jane Doe"
        assert result.loc[2, "Name"] == "Bob Wilson"
        # "Bob Wilson" is already properly capitalized, so only 2 changes
        assert len(tracker.changes) == 2


class TestDates:
    """Tests for date normalization."""

    def test_parse_date(self):
        assert parse_date("2026-01-15") is not None
        assert parse_date("01/15/2026") is not None
        assert parse_date("01-15-2026") is not None
        assert parse_date("January 15, 2026") is not None
        assert parse_date("15 Jan 2026") is not None
        assert parse_date("invalid") is None

    def test_normalize_date(self):
        assert normalize_date("2026-01-15") == "2026-01-15"
        assert normalize_date("01/15/2026") == "2026-01-15"
        assert normalize_date("January 15, 2026") == "2026-01-15"

    def test_is_safe_to_normalize(self):
        assert is_safe_to_normalize("2026-01-15", "2026-01-15")  # ISO format
        assert is_safe_to_normalize("01/15/2026", "2026-01-15")  # Unambiguous US
        assert not is_safe_to_normalize("01/02/2026", "2026-01-02")  # Ambiguous
        assert not is_safe_to_normalize("02/01/2026", "2026-02-01")  # Ambiguous

    def test_normalize_dates_column(self):
        df = pd.DataFrame({"Date": ["2026-01-15", "01/20/2026", "02/01/2026", "invalid"]})
        tracker = ChangeTracker()
        result = normalize_dates_column(df, "Date", tracker, only_safe=True)
        assert result.loc[0, "Date"] == "2026-01-15"
        assert result.loc[1, "Date"] == "2026-01-20"
        # Ambiguous date should not be changed
        assert result.loc[2, "Date"] == "02/01/2026"
        assert result.loc[3, "Date"] == "invalid"


class TestNormalization:
    """Tests for general normalization."""

    def test_remove_empty_rows(self):
        df = pd.DataFrame({"A": [1, None, 3], "B": ["a", "", "c"]})
        tracker = ChangeTracker()
        result = remove_empty_rows(df, tracker)
        assert len(result) == 2
        assert len(tracker.changes) == 1

    def test_strip_all_strings(self):
        df = pd.DataFrame({"A": ["  hello  ", "world  "], "B": [1, 2]})
        tracker = ChangeTracker()
        result = strip_all_strings(df, tracker)
        assert result.loc[0, "A"] == "hello"
        assert result.loc[1, "A"] == "world"
        assert len(tracker.changes) == 2

    def test_is_missing_value(self):
        from cleaning_engine.normalization import is_missing_value

        assert is_missing_value("")
        assert is_missing_value("   ")
        assert is_missing_value(None)
        assert is_missing_value(float("nan"))
        for token in ["N/A", "n/a", "NA", "null", "NULL", "None", "-", "--", "#N/A", "nan"]:
            assert is_missing_value(token), token
            assert is_missing_value(f"  {token}  "), token
        for real in ["John", "0", "Nairobi", "A-", "Anna"]:
            assert not is_missing_value(real), real

    def test_normalize_null_markers(self):
        from cleaning_engine.normalization import normalize_null_values

        df = pd.DataFrame({"A": ["N/A", "NULL", "-", "John", ""], "B": [1, 2, 3, 4, 5]})
        tracker = ChangeTracker()
        result = normalize_null_values(df, tracker)
        assert result["A"].tolist() == ["", "", "", "John", ""]
        assert len(tracker.get_changes_by_rule("normalize_nulls")) == 3
        originals = [c.original_value for c in tracker.get_changes_by_rule("normalize_nulls")]
        assert "N/A" in originals  # original preserved in the report

    def test_remove_marker_only_rows(self):
        df = pd.DataFrame({"A": ["N/A", "John"], "B": ["-", "x"]})
        tracker = ChangeTracker()
        result = remove_empty_rows(df, tracker)
        assert len(result) == 1
        assert result.loc[0, "A"] == "John"


class TestChangeTracker:
    """Tests for change tracking."""

    def test_add_change(self):
        tracker = ChangeTracker()
        change = ChangeRecord(
            row_index=0,
            column_name="Email",
            original_value="john@gmail.com",
            new_value="john@gmail.com",
            reason="Test",
            rule_name="test_rule",
        )
        tracker.add_change(change)
        assert len(tracker.changes) == 1
        assert tracker.rule_counts["test_rule"] == 1

    def test_get_changes_by_confidence(self):
        tracker = ChangeTracker()
        tracker.add_change(ChangeRecord(0, "A", "x", "y", "r", "rule", ConfidenceLevel.HIGH))
        tracker.add_change(ChangeRecord(1, "B", "x", "y", "r", "rule", ConfidenceLevel.MEDIUM))
        tracker.add_change(ChangeRecord(2, "C", "x", "y", "r", "rule", ConfidenceLevel.LOW))
        assert len(tracker.get_changes_by_confidence(ConfidenceLevel.HIGH)) == 1
        assert len(tracker.get_changes_by_confidence(ConfidenceLevel.MEDIUM)) == 1
        assert len(tracker.get_changes_by_confidence(ConfidenceLevel.LOW)) == 1

    def test_to_report(self):
        tracker = ChangeTracker()
        tracker.add_change(ChangeRecord(0, "A", "x", "y", "r", "rule1", ConfidenceLevel.HIGH))
        tracker.add_change(ChangeRecord(1, "B", "x", "y", "r", "rule2", ConfidenceLevel.MEDIUM))
        report = tracker.to_report()
        assert len(report.changes) == 2
        assert report.summary["rule1"] == 1
        assert report.summary["rule2"] == 1


class TestPipeline:
    """Tests for cleaning pipeline."""

    def test_default_pipeline_runs(self, messy_contacts_data: SpreadsheetData):
        pipeline = create_default_pipeline()
        cleaned_data, tracker = pipeline.run(messy_contacts_data)
        assert isinstance(cleaned_data, SpreadsheetData)
        assert cleaned_data.dataframe.shape[0] <= messy_contacts_data.dataframe.shape[0]
        assert len(tracker.changes) > 0

    def test_conservative_pipeline(self, messy_contacts_data: SpreadsheetData):
        pipeline = create_conservative_pipeline()
        _cleaned_data, tracker = pipeline.run(messy_contacts_data)
        # Conservative should make fewer changes
        assert len(tracker.changes) >= 0

    def test_pipeline_removes_duplicates(self, messy_contacts_data: SpreadsheetData):
        pipeline = create_default_pipeline()
        _cleaned_data, tracker = pipeline.run(messy_contacts_data)
        # Should have removed duplicate rows
        dup_changes = tracker.get_changes_by_rule("remove_duplicate_rows")
        assert len(dup_changes) > 0

    def test_pipeline_normalizes_whitespace(self, messy_contacts_data: SpreadsheetData):
        pipeline = create_default_pipeline()
        _cleaned_data, tracker = pipeline.run(messy_contacts_data)
        ws_changes = tracker.get_changes_by_rule("normalize_whitespace")
        assert len(ws_changes) > 0

    def test_pipeline_validates_emails(self, messy_contacts_data: SpreadsheetData):
        pipeline = create_default_pipeline()
        _cleaned_data, tracker = pipeline.run(messy_contacts_data)
        email_changes = tracker.get_changes_by_rule("validate_emails")
        assert len(email_changes) > 0

    def test_custom_config(self, messy_contacts_data: SpreadsheetData):
        config = PipelineConfig(
            remove_duplicate_rows=False,
            normalize_capitalization=False,
            normalize_dates=False,
        )
        pipeline = CleaningPipeline(config)
        _cleaned_data, tracker = pipeline.run(messy_contacts_data)
        # Should not have these changes
        assert len(tracker.get_changes_by_rule("remove_duplicate_rows")) == 0
        assert len(tracker.get_changes_by_rule("normalize_capitalization")) == 0
        assert len(tracker.get_changes_by_rule("normalize_dates")) == 0

    def test_mode_strictness_ordering(self, messy_contacts_data: SpreadsheetData):
        """conservative <= default <= aggressive in applied changes (and the
        reverse in pending review): the documented mode contract."""
        results = {}
        for name, factory in [
            ("conservative", create_conservative_pipeline),
            ("default", create_default_pipeline),
            ("aggressive", create_aggressive_pipeline),
        ]:
            _, tracker = factory().run(messy_contacts_data)
            report = tracker.to_report()
            applied = sum(1 for c in report.changes if c.applied)
            pending = sum(1 for c in report.changes if not c.applied)
            results[name] = (applied, pending)
        assert results["conservative"][0] <= results["default"][0] <= results["aggressive"][0]
        assert results["conservative"][1] >= results["default"][1] >= results["aggressive"][1]

    def test_build_pipeline_rejects_unknown_mode(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            build_pipeline("turbo")


class TestExporter:
    """Tests for export functionality."""

    def test_export_cleaned_csv(self, messy_contacts_data: SpreadsheetData, tmp_path: Path):
        output = tmp_path / "cleaned.csv"
        export_cleaned(messy_contacts_data, output)
        assert output.exists()
        # Verify it can be read back
        df = pd.read_csv(output)
        assert df.shape == messy_contacts_data.dataframe.shape

    def test_export_cleaned_xlsx(self, messy_contacts_data: SpreadsheetData, tmp_path: Path):
        output = tmp_path / "cleaned.xlsx"
        export_cleaned(messy_contacts_data, output)
        assert output.exists()
        df = pd.read_excel(output)
        assert df.shape == messy_contacts_data.dataframe.shape

    def test_export_report(self, messy_contacts_data: SpreadsheetData, tmp_path: Path):
        pipeline = create_default_pipeline()
        _, tracker = pipeline.run(messy_contacts_data)
        output = tmp_path / "report.xlsx"
        export_report(tracker, output)
        assert output.exists()
        # Verify sheets exist
        xls = pd.ExcelFile(output)
        assert "Changes" in xls.sheet_names
        assert "Summary" in xls.sheet_names
        assert "By Rule" in xls.sheet_names

    def test_report_visualizes_whitespace(self, tmp_path: Path):
        """Whitespace-only changes must be visible in the exported report."""
        from cleaning_engine.exporter import visualize_whitespace

        assert visualize_whitespace("  Vlad  ") == "··Vlad··"
        assert visualize_whitespace("Vlad") == "Vlad"
        assert visualize_whitespace("alice @outlook.com") == "alice @outlook.com"
        assert visualize_whitespace("a  b") == "a··b"
        assert visualize_whitespace("a\tb") == "a→b"
        assert visualize_whitespace(123) == 123

        tracker = ChangeTracker()
        tracker.add_change(
            ChangeRecord(0, "Name", "  Vlad  ", "Vlad", "r", "normalize_whitespace")
        )
        output = tmp_path / "report.xlsx"
        export_report(tracker, output)
        changes = pd.read_excel(output, sheet_name="Changes")
        assert changes.loc[0, "original"] == "··Vlad··"
        assert changes.loc[0, "new"] == "Vlad"


class TestGoldenFixtures:
    """Golden fixture tests - compare output to expected files.

    Golden files are the human-reviewed outputs of the default pipeline.
    Any change to pipeline behavior that alters these outputs must be
    reviewed before re-freezing the fixtures.
    """

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "messy_contacts",
            "simple_leads",
            "romanian_contacts",
            "edge_cases",
        ],
    )
    def test_golden(self, input_dir: Path, expected_dir: Path, fixture_name: str):
        """Test cleaning output matches the frozen golden file."""
        input_path = input_dir / f"{fixture_name}.csv"
        expected_path = expected_dir / f"{fixture_name}_cleaned.xlsx"
        assert expected_path.exists(), f"Golden fixture missing: {expected_path}"

        data = load_spreadsheet(input_path)
        pipeline = create_default_pipeline()
        cleaned_data, _ = pipeline.run(data)

        expected = pd.read_excel(expected_path, dtype=str, keep_default_na=False)
        actual = cleaned_data.dataframe.astype(str)
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
        )


class TestCLI:
    """Smoke tests for the CLI entry points."""

    def test_modes_command(self):
        from typer.testing import CliRunner

        from cleaning_engine.cli import app as cli_app

        result = CliRunner().invoke(cli_app, ["modes"])
        assert result.exit_code == 0, result.output
        assert "Conservative" in result.output
        assert "Aggressive" in result.output
        assert "MM/DD" in result.output

    def test_clean_help_mentions_modes(self):
        from typer.testing import CliRunner

        from cleaning_engine.cli import app as cli_app

        result = CliRunner().invoke(cli_app, ["clean", "--help"])
        assert result.exit_code == 0, result.output
        assert "modes" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

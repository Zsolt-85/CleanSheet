"""Test configuration and fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from cleaning_engine import (
    CleaningPipeline,
    create_conservative_pipeline,
    create_default_pipeline,
    load_spreadsheet,
)
from cleaning_engine.models import SpreadsheetData


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def input_dir(fixtures_dir: Path) -> Path:
    """Path to input fixtures."""
    return fixtures_dir / "input"


@pytest.fixture
def expected_dir(fixtures_dir: Path) -> Path:
    """Path to expected output fixtures."""
    return fixtures_dir / "expected"


@pytest.fixture
def messy_contacts_path(input_dir: Path) -> Path:
    """Path to messy contacts CSV."""
    return input_dir / "messy_contacts.csv"


@pytest.fixture
def simple_leads_path(input_dir: Path) -> Path:
    """Path to simple leads CSV."""
    return input_dir / "simple_leads.csv"


@pytest.fixture
def romanian_contacts_path(input_dir: Path) -> Path:
    """Path to Romanian contacts CSV."""
    return input_dir / "romanian_contacts.csv"


@pytest.fixture
def edge_cases_path(input_dir: Path) -> Path:
    """Path to edge cases CSV."""
    return input_dir / "edge_cases.csv"


@pytest.fixture
def messy_contacts_data(messy_contacts_path: Path) -> SpreadsheetData:
    """Load messy contacts as SpreadsheetData."""
    return load_spreadsheet(messy_contacts_path)


@pytest.fixture
def simple_leads_data(simple_leads_path: Path) -> SpreadsheetData:
    """Load simple leads as SpreadsheetData."""
    return load_spreadsheet(simple_leads_path)


@pytest.fixture
def pipeline() -> CleaningPipeline:
    """Default cleaning pipeline."""
    return create_default_pipeline()


@pytest.fixture
def conservative_pipeline() -> CleaningPipeline:
    """Conservative cleaning pipeline."""
    return create_conservative_pipeline()


def assert_dataframes_equal(
    df1: pd.DataFrame, df2: pd.DataFrame, check_dtype: bool = False
) -> None:
    """Assert two DataFrames are equal, ignoring index."""
    pd.testing.assert_frame_equal(
        df1.reset_index(drop=True),
        df2.reset_index(drop=True),
        check_dtype=check_dtype,
        check_exact=False,
        rtol=1e-10,
    )

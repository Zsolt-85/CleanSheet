"""Tests for the CleanSheet FastAPI backend (Phase 2 MVP)."""

import io
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stats DB isolated per test: never touch the developer's real totals."""
    monkeypatch.setenv("CLEANSHEET_STATS_PATH", str(tmp_path / "stats.db"))


@pytest.fixture
def messy_csv_bytes() -> bytes:
    return (Path(__file__).parent / "fixtures" / "input" / "messy_contacts.csv").read_bytes()


def _upload(client: TestClient, content: bytes, filename: str):  # type: ignore[no-untyped-def]
    return client.post("/api/analyze", files={"file": (filename, content)})


class TestHealth:
    def test_health(self, client: TestClient):
        assert client.get("/api/health").json() == {"status": "ok"}

    def test_limits(self, client: TestClient):
        limits = client.get("/api/limits").json()
        assert limits["max_file_mb"] == 25
        assert ".csv" in limits["supported_extensions"]

    def test_index_serves_frontend(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Clean your customer list" in resp.text
        # language switcher present
        assert 'id="lang-en"' in resp.text
        assert 'id="lang-ro"' in resp.text

    def test_legal_pages(self, client: TestClient):
        for path in ("/privacy", "/terms"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            # bilingual content
            assert "Privacy" in resp.text or "Terms" in resp.text or "Confiden" in resp.text
            assert 'id="btn-ro"' in resp.text


class TestAnalyze:
    def test_analyze_ok(self, client: TestClient, messy_csv_bytes: bytes):
        resp = client.post("/api/analyze", files={"file": ("messy.csv", messy_csv_bytes)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["rows"] == 20
        assert data["columns"] == 7
        types = {c["name"]: c["inferred_type"] for c in data["column_types"]}
        assert types["Email"] == "email"
        assert types["Date"] == "date"
        assert "remove_duplicate_rows" in data["suggested_operations"]

    def test_analyze_bad_extension(self, client: TestClient):
        resp = client.post("/api/analyze", files={"file": ("notes.txt", b"hello")})
        assert resp.status_code == 400

    def test_analyze_empty_file(self, client: TestClient):
        resp = client.post("/api/analyze", files={"file": ("empty.csv", b"")})
        assert resp.status_code == 400

    def test_analyze_garbage_xlsx(self, client: TestClient):
        resp = client.post("/api/analyze", files={"file": ("bad.xlsx", bytes(range(256)) * 10)})
        assert resp.status_code == 400


class TestClean:
    def test_clean_and_download(self, client: TestClient, messy_csv_bytes: bytes):
        resp = client.post(
            "/api/clean",
            files={"file": ("messy.csv", messy_csv_bytes)},
            data={"mode": "default"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rows_before"] == 20
        assert data["rows_after"] == 12
        assert data["applied_changes"] > 0
        assert "remove_duplicate_rows" in data["by_rule"]

        # Download cleaned file: valid xlsx that opens with expected shape
        dl = client.get(data["download_cleaned_url"])
        assert dl.status_code == 200
        assert dl.content[:2] == b"PK"  # zip container = xlsx
        df = pd.read_excel(io.BytesIO(dl.content))
        assert df.shape[0] == 12

        # Download report
        rep = client.get(data["download_report_url"])
        assert rep.status_code == 200
        xls = pd.ExcelFile(io.BytesIO(rep.content))
        assert "Changes" in xls.sheet_names

        # Files are single-use: second download is gone
        assert client.get(data["download_cleaned_url"]).status_code == 404
        assert client.get(data["download_report_url"]).status_code == 404

    def test_clean_conservative_mode(self, client: TestClient, messy_csv_bytes: bytes):
        resp = client.post(
            "/api/clean",
            files={"file": ("messy.csv", messy_csv_bytes)},
            data={"mode": "conservative"},
        )
        assert resp.status_code == 200
        assert resp.json()["rows_after"] <= 20

    def test_clean_bad_mode(self, client: TestClient, messy_csv_bytes: bytes):
        resp = client.post(
            "/api/clean",
            files={"file": ("messy.csv", messy_csv_bytes)},
            data={"mode": "turbo"},
        )
        assert resp.status_code == 400

    def test_clean_bad_file(self, client: TestClient):
        resp = client.post("/api/clean", files={"file": ("bad.xlsx", b"not an excel file")})
        assert resp.status_code == 400

    def test_oversized_rejected(
        self, client: TestClient, messy_csv_bytes: bytes, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 10)
        resp = client.post("/api/clean", files={"file": ("messy.csv", messy_csv_bytes)})
        assert resp.status_code == 413

    def test_unknown_token(self, client: TestClient):
        assert client.get("/api/download/nope/cleaned").status_code == 404
        assert client.get("/api/download/nope/report").status_code == 404
        assert client.get("/api/download/nope/other").status_code == 404


class TestModes:
    """Mode semantics endpoint: single source of truth for the frontend."""

    def test_modes_shape(self, client: TestClient):
        data = client.get("/api/modes").json()
        assert data["default_mode"] == "default"
        ids = [m["id"] for m in data["modes"]]
        assert ids == ["conservative", "default", "aggressive"]
        for m in data["modes"]:
            assert m["name"] and m["tagline"] and m["details"]
        aggressive = next(m for m in data["modes"] if m["id"] == "aggressive")
        assert "warning" in aggressive and "MM/DD" in aggressive["warning"]
        # Comparison covers every mode id
        assert data["comparison"]
        for row in data["comparison"]:
            assert row["operation"]
            for mode_id in ids:
                assert row[mode_id]
        assert len(data["guarantees"]) >= 3

    def test_modes_romanian(self, client: TestClient):
        data = client.get("/api/modes", params={"lang": "ro"}).json()
        assert data["lang"] == "ro"
        names = {m["id"]: m["name"] for m in data["modes"]}
        assert names == {
            "conservative": "Conservator",
            "default": "Standard",
            "aggressive": "Agresiv",
        }
        ops = [row["operation"] for row in data["comparison"]]
        assert "Elimină rândurile goale" in ops
        assert any("șters" in g or "șterg" in g or "șterse" in g for g in data["guarantees"])

    def test_modes_unknown_lang_falls_back_to_english(self, client: TestClient):
        data = client.get("/api/modes", params={"lang": "xx"}).json()
        assert data["lang"] == "en"


class TestStats:
    """Anonymous aggregate counters: real totals, no user data."""

    def test_stats_shape(self, client: TestClient):
        assert client.get("/api/stats").json() == {
            "jobs_completed": 0,
            "rows_in": 0,
            "rows_out": 0,
            "changes_applied": 0,
            "public_counter_threshold": 500,
        }

    def test_clean_increments_stats(self, client: TestClient, messy_csv_bytes: bytes):
        resp = client.post(
            "/api/clean",
            files={"file": ("messy.csv", messy_csv_bytes)},
            data={"mode": "default"},
        )
        assert resp.status_code == 200
        data = client.get("/api/stats").json()
        assert data["jobs_completed"] == 1
        assert data["rows_in"] == 20
        assert data["rows_out"] == 12
        assert data["changes_applied"] > 0

    def test_stats_failure_never_breaks_clean(
        self, client: TestClient, messy_csv_bytes: bytes, monkeypatch: pytest.MonkeyPatch
    ):
        import backend.app as app_module

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("stats db gone")

        monkeypatch.setattr(app_module, "record_cleaning", _boom)
        resp = client.post("/api/clean", files={"file": ("messy.csv", messy_csv_bytes)})
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

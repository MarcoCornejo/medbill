"""Tests for the MedBill CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from medbill.cli import main


@pytest.fixture
def dummy_file(tmp_path: Path) -> Path:
    """Create a dummy file to scan."""
    f = tmp_path / "bill.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    return f


class TestCLI:
    def test_no_args_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = main([])
        assert ret == 0
        captured = capsys.readouterr()
        assert "medbill" in captured.out.lower()

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_scan_file_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = main(["scan", "/nonexistent/bill.pdf"])
        assert ret == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_scan_text_output(self, dummy_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        ret = main(["scan", str(dummy_file)])
        assert ret == 0
        captured = capsys.readouterr()
        output = captured.out

        # Should show document info
        assert "MEDICAL_BILL" in output
        assert "Memorial Regional Hospital" in output

        # Should show errors
        assert "ISSUES FOUND" in output
        assert "DUPLICATE_CHARGE" in output

        # Should show price benchmarks
        assert "PRICE COMPARISON" in output
        assert "Medicare" in output

    def test_scan_json_output(self, dummy_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        ret = main(["scan", "--json", str(dummy_file)])
        assert ret == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert data["extraction"]["document_type"] == "MEDICAL_BILL"
        assert len(data["errors"]) > 0
        assert len(data["extraction"]["line_items"]) == 6
        assert len(data["price_benchmarks"]) > 0


class TestCLIIntegration:
    """End-to-end: file → extract → analyze → output.

    Validates the full pipeline works as a vertical slice.
    """

    def test_full_pipeline_produces_actionable_output(
        self, dummy_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ret = main(["scan", "--json", str(dummy_file)])
        assert ret == 0

        data = json.loads(capsys.readouterr().out)

        # Extraction is complete
        extraction = data["extraction"]
        assert extraction["document_type"] == "MEDICAL_BILL"
        assert len(extraction["line_items"]) == 6
        assert extraction["totals"]["total_billed"] is not None

        # Rule engine found errors
        errors = data["errors"]
        error_types = {e["error_type"] for e in errors}
        assert "DUPLICATE_CHARGE" in error_types  # Two 85025 on same date
        assert "UNBUNDLED_CODES" in error_types  # 80053 + 82565

        # Price benchmarks computed
        benchmarks = data["price_benchmarks"]
        assert len(benchmarks) > 0
        for b in benchmarks:
            assert b["billed_amount"] is not None
            assert b["medicare_rate"] is not None
            assert b["ratio"] > 0

        # Overcharge estimated
        assert float(data["total_estimated_overcharge"]) > 0

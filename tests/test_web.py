"""Tests for the MedBill web application."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from medbill.web.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_health_check(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestIndex:
    def test_landing_page(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "MedBill" in resp.text
        assert "Scan your medical bill" in resp.text
        assert "Nothing is stored" in resp.text


class TestScan:
    def test_scan_with_mock_extractor(self, client: TestClient) -> None:
        fake_pdf = BytesIO(b"%PDF-1.4 fake content")
        resp = client.post(
            "/scan",
            files={"file": ("bill.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.text

        # Should show errors (mock data has duplicates + NCCI violations)
        assert "potential issue" in body

        # Should show line items
        assert "99214" in body
        assert "85025" in body
        assert "Memorial Regional Hospital" not in body  # PII not in template
        assert "Jane Rodriguez" not in body  # Patient name not displayed

        # Should show dollar amounts
        assert "$350.00" in body or "350.00" in body

    def test_scan_shows_duplicate_error(self, client: TestClient) -> None:
        fake_pdf = BytesIO(b"fake")
        resp = client.post(
            "/scan",
            files={"file": ("bill.pdf", fake_pdf, "application/pdf")},
        )
        assert "Duplicate Charge" in resp.text or "DUPLICATE" in resp.text

    def test_scan_shows_unbundled_error(self, client: TestClient) -> None:
        fake_pdf = BytesIO(b"fake")
        resp = client.post(
            "/scan",
            files={"file": ("bill.pdf", fake_pdf, "application/pdf")},
        )
        # Mock data has 80053 + 82565 (CMP includes creatinine)
        assert "Unbundled" in resp.text or "NCCI" in resp.text

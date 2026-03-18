"""Integration tests for the FastAPI app with debug middleware pipeline."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clean_snapshots(tmp_path):
    """Redirect snapshot storage to tmp_path and clean up after each test."""
    snapshots_dir = tmp_path / "error_snapshots"
    with patch("app.debug.error_capture.SNAPSHOTS_DIR", snapshots_dir):
        yield snapshots_dir


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_has_correlation_id(self, client):
        response = client.get("/health")
        assert "x-correlation-id" in response.headers


class TestErrorPipeline:
    def test_test_error_returns_500(self, client):
        response = client.get("/debug/test-error")
        assert response.status_code == 500

    def test_test_error_body_has_correlation_id(self, client):
        response = client.get("/debug/test-error")
        body = response.json()
        assert "correlation_id" in body
        assert body["correlation_id"].startswith("req-")

    def test_test_error_header_matches_body(self, client):
        response = client.get("/debug/test-error")
        body = response.json()
        assert response.headers["x-correlation-id"] == body["correlation_id"]

    def test_test_error_creates_snapshot(self, client, _clean_snapshots):
        response = client.get("/debug/test-error")
        cid = response.json()["correlation_id"]
        snapshot_path = _clean_snapshots / f"{cid}.json"
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text())
        assert snapshot["error_type"] == "PetPalError"
        assert snapshot["correlation_id"] == cid

    def test_custom_correlation_id_propagated(self, client):
        custom_cid = "req-custom123456"
        response = client.get(
            "/debug/test-error",
            headers={"X-Correlation-ID": custom_cid},
        )
        assert response.headers["x-correlation-id"] == custom_cid
        assert response.json()["correlation_id"] == custom_cid

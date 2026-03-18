"""Tests for error_types, fingerprint, and error_capture modules."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.debug.error_types import (
    AgentError,
    AuthError,
    DatabaseError,
    ErrorCategory,
    ExternalAPIError,
    PetPalError,
    ValidationError,
)
from app.debug.fingerprint import compute_fingerprint
from app.debug.error_capture import (
    ErrorSnapshot,
    capture_error,
    load_snapshot,
    save_snapshot,
)


# --- error_types tests ---

class TestErrorTypes:
    def test_agent_error_category(self):
        err = AgentError("llm failed")
        assert err.category == ErrorCategory.AGENT_LLM

    def test_database_error_category(self):
        err = DatabaseError("connection lost")
        assert err.category == ErrorCategory.DATABASE

    def test_external_api_error_category(self):
        err = ExternalAPIError("timeout")
        assert err.category == ErrorCategory.EXTERNAL_API

    def test_auth_error_category(self):
        err = AuthError("bad token")
        assert err.category == ErrorCategory.AUTH

    def test_validation_error_category(self):
        err = ValidationError("invalid field")
        assert err.category == ErrorCategory.VALIDATION

    def test_petpal_error_default_category(self):
        err = PetPalError("generic")
        assert err.category == ErrorCategory.UNKNOWN

    def test_module_auto_inference(self):
        """Errors created here should infer this test module."""
        err = AgentError("test")
        # Should contain the test module name, not error_types
        assert "test_error_system" in err.module

    def test_explicit_module(self):
        err = AgentError("test", module="my.custom.module")
        assert err.module == "my.custom.module"

    def test_context_default_empty(self):
        err = PetPalError("msg")
        assert err.context == {}

    def test_context_preserved(self):
        ctx = {"key": "value"}
        err = PetPalError("msg", context=ctx)
        assert err.context == ctx

    def test_is_exception(self):
        with pytest.raises(AgentError):
            raise AgentError("boom")


# --- fingerprint tests ---

class TestFingerprint:
    def test_stable_output(self):
        """Same inputs always produce the same fingerprint."""
        fp1 = compute_fingerprint("AgentError", "app.agent", "LLM call failed")
        fp2 = compute_fingerprint("AgentError", "app.agent", "LLM call failed")
        assert fp1 == fp2

    def test_length(self):
        fp = compute_fingerprint("E", "m", "msg")
        assert len(fp) == 16

    def test_hex_chars(self):
        fp = compute_fingerprint("E", "m", "msg")
        assert all(c in "0123456789abcdef" for c in fp)

    def test_uuid_normalization(self):
        """Different UUIDs in the message should yield the same fingerprint."""
        fp1 = compute_fingerprint(
            "AgentError", "mod",
            "Failed for user 550e8400-e29b-41d4-a716-446655440000"
        )
        fp2 = compute_fingerprint(
            "AgentError", "mod",
            "Failed for user a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert fp1 == fp2

    def test_number_normalization(self):
        fp1 = compute_fingerprint("E", "m", "retry after 5 seconds")
        fp2 = compute_fingerprint("E", "m", "retry after 30 seconds")
        assert fp1 == fp2

    def test_path_normalization(self):
        fp1 = compute_fingerprint("E", "m", "file /tmp/abc.log missing")
        fp2 = compute_fingerprint("E", "m", "file /var/log/xyz.log missing")
        assert fp1 == fp2

    def test_different_types_differ(self):
        fp1 = compute_fingerprint("AgentError", "mod", "fail")
        fp2 = compute_fingerprint("DatabaseError", "mod", "fail")
        assert fp1 != fp2


# --- error_capture tests ---

class TestErrorSnapshot:
    def test_dataclass_fields(self):
        """ErrorSnapshot has all required fields."""
        snap = ErrorSnapshot(
            correlation_id="req-abc",
            timestamp="2026-01-01T00:00:00Z",
            category="unknown",
            module="test",
            error_type="Exception",
            error_message="boom",
            traceback="",
            fingerprint="abcd1234abcd1234",
            request_data={},
            correlation_context={},
        )
        assert snap.correlation_id == "req-abc"
        assert snap.agent_state is None
        assert snap.db_context is None


class TestCaptureError:
    @patch("app.debug.correlation.get_correlation_id", return_value="req-test123")
    @patch("app.debug.correlation.get_correlation_context", return_value={
        "correlation_id": "req-test123",
        "user_id": "u1",
        "pet_id": "p1",
    })
    def test_capture_petpal_error(self, mock_ctx, mock_cid):
        try:
            raise AgentError("LLM timeout", context={"model": "gpt-4"})
        except AgentError as exc:
            snap = capture_error(exc, request_data={"path": "/api/chat"})

        assert snap.correlation_id == "req-test123"
        assert snap.category == "agent_llm"
        assert snap.error_type == "AgentError"
        assert snap.error_message == "LLM timeout"
        assert snap.request_data == {"path": "/api/chat"}
        assert len(snap.fingerprint) == 16
        assert "AgentError" in snap.traceback or "LLM timeout" in snap.traceback

    @patch("app.debug.correlation.get_correlation_id", return_value="req-plain")
    @patch("app.debug.correlation.get_correlation_context", return_value={
        "correlation_id": "req-plain",
        "user_id": "",
        "pet_id": "",
    })
    def test_capture_plain_exception(self, mock_ctx, mock_cid):
        try:
            raise RuntimeError("unexpected")
        except RuntimeError as exc:
            snap = capture_error(exc)

        assert snap.category == "unknown"
        assert snap.error_type == "RuntimeError"


class TestSnapshotPersistence:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.debug.error_capture.SNAPSHOTS_DIR", tmp_path
        )
        snap = ErrorSnapshot(
            correlation_id="req-roundtrip",
            timestamp="2026-01-01T00:00:00Z",
            category="db",
            module="app.db",
            error_type="DatabaseError",
            error_message="connection lost",
            traceback="Traceback ...",
            fingerprint="aabb112233445566",
            request_data={"method": "GET"},
            correlation_context={"correlation_id": "req-roundtrip"},
            agent_state={"step": 3},
            db_context={"query": "SELECT 1"},
        )

        path = save_snapshot(snap)
        assert path.exists()
        assert path.name == "req-roundtrip.json"

        # Verify JSON is valid
        data = json.loads(path.read_text())
        assert data["category"] == "db"
        assert data["agent_state"] == {"step": 3}

        # Roundtrip via load
        loaded = load_snapshot("req-roundtrip")
        assert loaded.correlation_id == snap.correlation_id
        assert loaded.error_message == snap.error_message
        assert loaded.agent_state == snap.agent_state
        assert loaded.db_context == snap.db_context

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        target = tmp_path / "nested" / "snapshots"
        monkeypatch.setattr("app.debug.error_capture.SNAPSHOTS_DIR", target)

        snap = ErrorSnapshot(
            correlation_id="req-mkdir",
            timestamp="2026-01-01T00:00:00Z",
            category="unknown",
            module="test",
            error_type="Exception",
            error_message="test",
            traceback="",
            fingerprint="0000000000000000",
            request_data={},
            correlation_context={},
        )
        path = save_snapshot(snap)
        assert path.exists()

"""Tests for the test_generator module."""

from pathlib import Path

from app.debug.error_capture import ErrorSnapshot
from app.debug.test_generator import generate_test, generate_test_file


def _make_snapshot(**overrides) -> ErrorSnapshot:
    defaults = dict(
        correlation_id="req-gen-001",
        timestamp="2026-01-15T10:30:00Z",
        category="unknown",
        module="app.some_module",
        error_type="Exception",
        error_message="something broke",
        traceback="Traceback ...",
        fingerprint="aabb112233445566",
        request_data={"path": "/api/test"},
        correlation_context={"correlation_id": "req-gen-001"},
    )
    defaults.update(overrides)
    return ErrorSnapshot(**defaults)


class TestGenerateAgentTest:
    def test_produces_valid_python(self):
        snap = _make_snapshot(
            category="agent_llm",
            error_type="AgentError",
            error_message="LLM timeout",
            fingerprint="aaaa111122223333",
            agent_state={"raw_response": "error from model"},
        )
        code = generate_test(snap)
        compile(code, "<generated>", "exec")

    def test_contains_mock_and_imports(self):
        snap = _make_snapshot(
            category="agent_llm",
            error_type="AgentError",
            error_message="LLM timeout",
            fingerprint="aaaa111122223333",
            agent_state={"raw_response": "error from model"},
        )
        code = generate_test(snap)
        assert "litellm.acompletion" in code
        assert "from unittest.mock import" in code
        assert "pytest.mark.asyncio" in code
        assert "AgentError" in code


class TestGenerateDatabaseTest:
    def test_produces_valid_python(self):
        snap = _make_snapshot(
            category="db",
            error_type="DatabaseError",
            error_message="connection lost",
            fingerprint="bbbb111122223333",
            db_context={"query": "SELECT * FROM pets WHERE id = ?", "params": {"id": 42}},
        )
        code = generate_test(snap)
        compile(code, "<generated>", "exec")

    def test_contains_query_context(self):
        snap = _make_snapshot(
            category="db",
            error_type="DatabaseError",
            error_message="connection lost",
            fingerprint="bbbb111122223333",
            db_context={"query": "SELECT * FROM pets WHERE id = ?", "params": {"id": 42}},
        )
        code = generate_test(snap)
        assert "SELECT * FROM pets" in code
        assert "DatabaseError" in code


class TestGenerateExternalAPITest:
    def test_produces_valid_python(self):
        snap = _make_snapshot(
            category="external_api",
            error_type="ExternalAPIError",
            error_message="service unavailable",
            fingerprint="cccc111122223333",
        )
        code = generate_test(snap)
        compile(code, "<generated>", "exec")


class TestGenerateDefaultTest:
    def test_produces_valid_python(self):
        snap = _make_snapshot(
            category="validation",
            fingerprint="dddd111122223333",
        )
        code = generate_test(snap)
        compile(code, "<generated>", "exec")


class TestGenerateTestFile:
    def test_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.test_generator.GENERATED_TESTS_DIR", tmp_path)
        snap = _make_snapshot(
            category="agent_llm",
            error_type="AgentError",
            error_message="LLM timeout",
            fingerprint="eeee111122223333",
            agent_state={"step": 1},
        )
        path = generate_test_file(snap)
        assert path is not None
        assert path.exists()
        assert "eeee111122223333" in path.name
        # Verify content is valid Python
        compile(path.read_text(), str(path), "exec")

    def test_deduplication(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.debug.test_generator.GENERATED_TESTS_DIR", tmp_path)
        snap = _make_snapshot(
            category="agent_llm",
            error_type="AgentError",
            error_message="LLM timeout",
            fingerprint="ffff111122223333",
            agent_state={},
        )
        first = generate_test_file(snap)
        assert first is not None

        second = generate_test_file(snap)
        assert second is None

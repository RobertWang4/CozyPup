"""Tests for core debug infrastructure: logging, correlation, and middleware."""

import json
import logging
import re

import pytest
from starlette.testclient import TestClient

from app.debug.correlation import (
    generate_correlation_id,
    get_correlation_context,
    get_correlation_id,
    set_correlation_id,
    set_pet_id,
    set_user_id,
)
from app.debug.logging_config import JSONFormatter, setup_logging


# --- correlation.py tests ---


class TestCorrelation:
    def setup_method(self):
        set_correlation_id("")
        set_user_id("")
        set_pet_id("")

    def test_generate_correlation_id_format(self):
        cid = generate_correlation_id()
        assert re.match(r"^req-[0-9a-f]{12}$", cid)

    def test_generate_correlation_id_unique(self):
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100

    def test_context_var_defaults(self):
        ctx = get_correlation_context()
        assert ctx["correlation_id"] == ""
        assert ctx["user_id"] == ""
        assert ctx["pet_id"] == ""

    def test_set_and_get_correlation_id(self):
        set_correlation_id("req-abc123def456")
        assert get_correlation_id() == "req-abc123def456"

    def test_get_correlation_context(self):
        set_correlation_id("req-test123test")
        set_user_id("user-42")
        set_pet_id("pet-7")
        ctx = get_correlation_context()
        assert ctx == {
            "correlation_id": "req-test123test",
            "user_id": "user-42",
            "pet_id": "pet-7",
        }


# --- logging_config.py tests ---


class TestJSONFormatter:
    def setup_method(self):
        self.formatter = JSONFormatter()

    def test_produces_valid_json(self):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=10, msg="hello world", args=(), exc_info=None,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"

    def test_required_fields_present(self):
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="test.py",
            lineno=5, msg="test msg", args=(), exc_info=None,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        for field in ("timestamp", "level", "module", "function", "line",
                       "correlation_id", "user_id", "pet_id", "message", "extra"):
            assert field in data, f"Missing field: {field}"

    def test_includes_correlation_context(self):
        set_correlation_id("req-fromlogtest")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="ctx test", args=(), exc_info=None,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        assert data["correlation_id"] == "req-fromlogtest"

    def test_includes_error_info(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="error", args=(), exc_info=exc_info,
        )
        output = self.formatter.format(record)
        data = json.loads(output)
        assert data["error"]["type"] == "ValueError"
        assert any("boom" in line for line in data["error"]["traceback"])

    def test_setup_logging_configures_root(self):
        setup_logging(level="WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_setup_logging_module_levels(self):
        setup_logging(module_levels={"app.agents": "DEBUG", "app.db": "DEBUG", "app.middleware": "INFO"})
        assert logging.getLogger("app.agents").level == logging.DEBUG
        assert logging.getLogger("app.db").level == logging.DEBUG
        assert logging.getLogger("app.middleware").level == logging.INFO


# --- middleware.py tests ---


def _make_app():
    """Create a minimal FastAPI app with all three middlewares."""
    from fastapi import FastAPI

    from app.debug.middleware import (
        CorrelationMiddleware,
        ErrorCaptureMiddleware,
        RequestLoggingMiddleware,
    )

    app = FastAPI()

    # Middleware is applied in reverse order — last added runs first
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(ErrorCaptureMiddleware)
    app.add_middleware(CorrelationMiddleware)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/fail")
    async def fail():
        raise RuntimeError("intentional failure")

    return app


class TestMiddleware:
    def setup_method(self):
        self.app = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_correlation_id_in_response_header(self):
        resp = self.client.get("/ok")
        assert resp.status_code == 200
        cid = resp.headers.get("X-Correlation-ID", "")
        assert re.match(r"^req-[0-9a-f]{12}$", cid)

    def test_user_id_header_propagated(self):
        resp = self.client.get("/ok", headers={"X-User-ID": "user-99"})
        assert resp.status_code == 200
        # Correlation ID should still be set
        assert resp.headers.get("X-Correlation-ID")

    def test_request_logging(self, caplog):
        with caplog.at_level(logging.INFO):
            self.client.get("/ok")
        messages = " ".join(caplog.messages)
        assert "GET" in messages
        assert "/ok" in messages
        assert "duration_ms" in messages

    def test_error_capture_returns_500(self):
        resp = self.client.get("/fail")
        assert resp.status_code == 500
        body = resp.json()
        assert "error" in body
        assert "correlation_id" in body
        assert re.match(r"^req-[0-9a-f]{12}$", body["correlation_id"])

"""Generate pytest test files from error snapshots."""

import json
from pathlib import Path

from .error_capture import ErrorSnapshot

GENERATED_TESTS_DIR = Path("tests/generated")


def generate_test(snapshot: ErrorSnapshot) -> str:
    """Return Python source for a pytest test based on the snapshot's category."""
    if snapshot.category == "agent_llm":
        return _generate_agent_test(snapshot)
    elif snapshot.category == "db":
        return _generate_database_test(snapshot)
    elif snapshot.category == "external_api":
        return _generate_external_api_test(snapshot)
    else:
        return _generate_default_test(snapshot)


def generate_test_file(snapshot: ErrorSnapshot) -> Path | None:
    """Write a generated test to disk, deduplicating by fingerprint.

    Returns the file path, or None if a test with the same fingerprint exists.
    """
    GENERATED_TESTS_DIR.mkdir(parents=True, exist_ok=True)

    for existing in GENERATED_TESTS_DIR.glob(f"test_*_{snapshot.fingerprint}.py"):
        return None

    ts = snapshot.timestamp.replace(":", "").replace("-", "").replace("T", "_").split(".")[0]
    filename = f"test_{ts}_{snapshot.fingerprint}.py"
    path = GENERATED_TESTS_DIR / filename
    path.write_text(generate_test(snapshot))
    return path


def _docstring_lines(snapshot: ErrorSnapshot) -> str:
    return (
        f'    """Auto-generated from error snapshot.\n'
        f"\n"
        f"    Correlation ID: {snapshot.correlation_id}\n"
        f"    Timestamp:      {snapshot.timestamp}\n"
        f"    Module:         {snapshot.module}\n"
        f"    Error:          {snapshot.error_type}: {snapshot.error_message}\n"
        f'    """'
    )


def _generate_agent_test(snapshot: ErrorSnapshot) -> str:
    agent_state = json.dumps(snapshot.agent_state or {}, indent=4)
    # Indent continuation lines of the JSON for inside the function body
    agent_state_indented = agent_state.replace("\n", "\n    ")

    lines = [
        "import pytest",
        "from unittest.mock import AsyncMock, patch",
        "",
        "from app.debug.error_types import AgentError",
        "",
        "",
        "@pytest.mark.asyncio",
        f"async def test_agent_error_{snapshot.fingerprint}():",
        _docstring_lines(snapshot),
        f"    mock_response = {agent_state_indented}",
        "",
        '    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:',
        "        mock_llm.return_value = mock_response",
        "        with pytest.raises(AgentError):",
        "            # TODO: call the agent function that triggered this error",
        f"            raise AgentError({snapshot.error_message!r})",
        "",
    ]
    return "\n".join(lines) + "\n"


def _generate_database_test(snapshot: ErrorSnapshot) -> str:
    db_context = snapshot.db_context or {}
    query = db_context.get("query", "-- unknown query")
    params = db_context.get("params", {})

    lines = [
        "import pytest",
        "from unittest.mock import MagicMock, patch",
        "",
        "from app.debug.error_types import DatabaseError",
        "",
        "",
        f"def test_database_error_{snapshot.fingerprint}():",
        _docstring_lines(snapshot),
        f"    # Query: {query}",
        f"    # Params: {json.dumps(params)}",
        "",
        "    # TODO: set up database state and execute the query",
        '    pytest.skip("Generated skeleton \\u2014 fill in database setup")',
        "",
    ]
    return "\n".join(lines) + "\n"


def _generate_external_api_test(snapshot: ErrorSnapshot) -> str:
    request_data = json.dumps(snapshot.request_data or {}, indent=4)
    request_data_indented = request_data.replace("\n", "\n    ")

    lines = [
        "import pytest",
        "from unittest.mock import AsyncMock, patch, MagicMock",
        "",
        "from app.debug.error_types import ExternalAPIError",
        "",
        "",
        "@pytest.mark.asyncio",
        f"async def test_external_api_error_{snapshot.fingerprint}():",
        _docstring_lines(snapshot),
        f"    request_data = {request_data_indented}",
        "",
        "    mock_response = MagicMock()",
        "    mock_response.status_code = 500",
        f'    mock_response.json.return_value = {{"error": {snapshot.error_message!r}}}',
        "",
        '    with patch("httpx.AsyncClient") as mock_client_cls:',
        "        mock_client = AsyncMock()",
        "        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)",
        "        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)",
        "        mock_client.request.return_value = mock_response",
        "",
        "        with pytest.raises(ExternalAPIError):",
        "            # TODO: call the function that makes the external API request",
        f"            raise ExternalAPIError({snapshot.error_message!r})",
        "",
    ]
    return "\n".join(lines) + "\n"


def _generate_default_test(snapshot: ErrorSnapshot) -> str:
    context = json.dumps(
        {
            "request_data": snapshot.request_data,
            "correlation_context": snapshot.correlation_context,
            "error_type": snapshot.error_type,
            "module": snapshot.module,
        },
        indent=4,
    )
    context_indented = context.replace("\n", "\n    ")
    request_data = json.dumps(snapshot.request_data or {}, indent=4)
    request_data_indented = request_data.replace("\n", "\n    ")

    lines = [
        "import pytest",
        "from unittest.mock import MagicMock, patch",
        "",
        "",
        f"def test_error_{snapshot.fingerprint}():",
        _docstring_lines(snapshot),
        f"    context = {context_indented}",
        "",
        f"    request_data = {request_data_indented}",
        "",
        "    # TODO: reproduce the error scenario",
        '    pytest.skip("Generated skeleton \\u2014 fill in reproduction steps")',
        "",
    ]
    return "\n".join(lines) + "\n"

import ast
from pathlib import Path

from app.agent_harness import client as harness_client
from tests.e2e import conftest as e2e_conftest


def test_e2e_conftest_reexports_harness_client_helpers():
    assert e2e_conftest.E2EClient is harness_client.AgentHarnessClient
    assert e2e_conftest.ChatResult is harness_client.ChatResult
    assert e2e_conftest._parse_sse_lines is harness_client.parse_sse_lines
    assert e2e_conftest._build_chat_result is harness_client.build_chat_result
    assert e2e_conftest.get_tools_called is harness_client.get_tools_called
    assert e2e_conftest.load_test_image is harness_client.load_test_image


def test_e2e_conftest_has_no_local_client_or_sse_parser_defs():
    source_path = Path(__file__).parent / "e2e" / "conftest.py"
    tree = ast.parse(source_path.read_text())
    top_level_defs = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "ChatResult" not in top_level_defs
    assert "E2EClient" not in top_level_defs
    assert "_parse_sse_lines" not in top_level_defs
    assert "_build_chat_result" not in top_level_defs

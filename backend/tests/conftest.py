"""Shared pytest config.

Production uses Postgres (JSONB, pgvector). Several tests spin up an
in-memory SQLite to avoid needing a live Postgres in CI. Register type
compilations so SQLite can accept schemas that reference Postgres-specific
types — the values still round-trip as JSON text, which is enough for the
assertions those tests make.
"""

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


def pytest_collection_modifyitems(config, items):
    """Deselect `rag_eval` tests unless the user explicitly opts in via `-m rag_eval`.

    The RAG retrieval eval hits the real database and the litellm embedding
    endpoint. It's slow and has external dependencies, so it must not run in
    the default `pytest` invocation or CI.
    """
    marker_expr = config.getoption("-m") or ""
    if "rag_eval" in marker_expr:
        return
    skip_marker = pytest.mark.skip(reason="rag_eval is opt-in; run with `pytest -m rag_eval`")
    for item in items:
        if "rag_eval" in item.keywords:
            item.add_marker(skip_marker)

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover — optional in environments without pgvector
    Vector = None


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


if Vector is not None:
    @compiles(Vector, "sqlite")
    def _compile_vector_sqlite(element, compiler, **kw):  # pragma: no cover
        # SQLite fixtures don't exercise vector ops; storing as blob is fine.
        return "BLOB"

"""Shared pytest config.

Production uses Postgres (JSONB, pgvector). Several tests spin up an
in-memory SQLite to avoid needing a live Postgres in CI. Register type
compilations so SQLite can accept schemas that reference Postgres-specific
types — the values still round-trip as JSON text, which is enough for the
assertions those tests make.
"""

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

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

"""Admin-only RAG observability endpoints.

Intentionally lives alongside — not inside — the richer `app/routers/admin/`
package because it authenticates off a simple shared-secret header
(`X-Admin-Token`) rather than the JWT-backed admin context used elsewhere.
Keeping the two auth styles on different routers avoids accidental
cross-use of the weaker auth.

Fail-closed: if `settings.admin_api_token` is unset the endpoint always
returns 403. Operators must set `ADMIN_API_TOKEN` to enable it.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import settings
from app.services.rag_stats import compute_rag_stats

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])


def _require_admin_token(x_admin_token: str | None) -> None:
    expected = settings.admin_api_token
    if not expected:
        # Fail closed — never expose stats when the token isn't configured.
        raise HTTPException(status_code=403, detail="admin endpoint disabled")
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="invalid admin token")


@router.get("/stats")
async def rag_stats(
    days: int = Query(7, ge=1, le=90),
    zero_recall_limit: int = Query(50, ge=0, le=500),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    """Aggregate RAG behavior over a recent time window.

    Surfaces zero-recall queries so product can triage content gaps.
    """
    _require_admin_token(x_admin_token)
    return await compute_rag_stats(
        days=days, zero_recall_limit=zero_recall_limit
    )

"""Observability routes: user inspect, trace fetch, errors recent, export, impersonate.

Phase 1 initial scope: user inspect only. Tasks B5/B6 will append trace, errors,
export, and impersonate routes to this same file.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Chat, ChatSession, Pet, User

from .deps import AdminContext, require_admin

obs_router = APIRouter(tags=["admin-obs"])

GCP_PROJECT = "cozypup-39487"
TRACE_LOGGER = "cozypup.trace"


def _gcloud_read(filter_expr: str, limit: int = 500) -> list[dict]:
    cmd = [
        "gcloud", "logging", "read", filter_expr,
        f"--project={GCP_PROJECT}", "--format=json", f"--limit={limit}", "--order=desc",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return []
        return json.loads(r.stdout) if r.stdout.strip() else []
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return []


def _parse_trace_entry(e: dict) -> dict | None:
    payload = e.get("jsonPayload") or {}
    try:
        return json.loads(payload.get("message", ""))
    except Exception:
        return None


def _since_to_timedelta(since: str) -> timedelta:
    if since == "all":
        return timedelta(days=365 * 10)
    n = int(since[:-1])
    unit = since[-1]
    return {"h": timedelta(hours=n), "d": timedelta(days=n)}[unit]


async def _resolve_user(db: AsyncSession, target: str) -> User:
    if "@" in target:
        row = await db.execute(select(User).where(User.email == target))
    else:
        try:
            uid = uuid.UUID(target)
            row = await db.execute(select(User).where(User.id == uid))
        except ValueError:
            try:
                row = await db.execute(select(User).where(User.id.cast(str).like(f"{target}%")))
            except Exception:
                raise HTTPException(status_code=404, detail="user not found")
    user = row.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def inspect_user(
    *,
    target: str,
    since: str,
    chats_mode: str,
    session_id: str | None,
    db: AsyncSession,
    gcloud_reader=_gcloud_read,
) -> dict:
    user = await _resolve_user(db, target)
    cutoff = datetime.now(timezone.utc) - _since_to_timedelta(since)

    # Pets
    pets = (await db.execute(select(Pet).where(Pet.user_id == user.id))).scalars().all()

    # Chats
    q = select(Chat).where(Chat.user_id == user.id, Chat.created_at >= cutoff)
    if session_id:
        q = q.where(Chat.session_id == uuid.UUID(session_id))
    q = q.order_by(Chat.created_at.asc())
    chats = (await db.execute(q)).scalars().all()

    # Errors from Cloud Logging
    filter_err = (
        f'logName=~"logs/run.googleapis.com" jsonPayload.user_id="{user.id}" '
        f'jsonPayload.log_type="error_snapshot" timestamp>="{cutoff.isoformat()}"'
    )
    error_entries = [p for p in (_parse_trace_entry(e) for e in gcloud_reader(filter_err)) if p]
    err_by_cid = {e.get("correlation_id"): e for e in error_entries}

    activity: list[dict] = []
    for c in chats:
        err = err_by_cid.get(c.correlation_id)
        role_val = c.role.value if hasattr(c.role, "value") else str(c.role)
        if chats_mode == "errors" and err is None:
            continue
        activity.append({
            "ts": c.created_at.isoformat(),
            "role": role_val,
            "session_id": str(c.session_id),
            "correlation_id": c.correlation_id,
            "content": c.content[:500] if c.content else "",
            "has_images": bool(c.image_urls),
            "error": {
                "module": (err.get("data") or {}).get("src_module") if err else None,
                "type": (err.get("data") or {}).get("error_type") if err else None,
            } if err else None,
        })
        if chats_mode == "recent" and len(activity) >= 20:
            break

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat(),
            "auth_provider": user.auth_provider,
            "is_admin": bool(user.is_admin),
        },
        "subscription": {
            "status": user.subscription_status,
            "product": user.subscription_product_id,
            "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
        },
        "pets": [{"id": str(p.id), "name": p.name, "species": p.species.value if hasattr(p.species, "value") else str(p.species), "breed": p.breed} for p in pets],
        "counters": {
            "messages_in_window": len(chats),
            "errors_in_window": len(error_entries),
        },
        "activity": activity,
    }


@obs_router.get("/users/{target}/inspect")
async def users_inspect(
    target: str,
    since: str = Query("24h"),
    chats: str = Query("recent", alias="chats"),
    session: str | None = Query(None),
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await inspect_user(
        target=target, since=since, chats_mode=chats, session_id=session, db=db,
        gcloud_reader=_gcloud_read,
    )
    return {"data": data, "audit_id": None, "env": "server"}


async def reconstruct_trace(
    correlation_id: str,
    *,
    gcloud_reader=_gcloud_read,
    db: AsyncSession,
    show_tools: bool = False,
    show_system_prompt: bool = False,
) -> dict:
    filter_expr = f'jsonPayload.correlation_id="{correlation_id}"'
    entries = [p for p in (_parse_trace_entry(e) for e in gcloud_reader(filter_expr, limit=500)) if p]
    entries.sort(key=lambda e: e.get("round") or 0)

    out: dict[str, Any] = {
        "correlation_id": correlation_id,
        "chat_request": None,
        "rounds": [],
        "chat_response": None,
        "error": None,
    }
    rounds_by_idx: dict[int, dict] = {}

    for e in entries:
        lt = e.get("log_type")
        data = e.get("data") or {}
        if lt == "chat_request":
            out["chat_request"] = data
        elif lt == "llm_request":
            idx = e.get("round") or 0
            r = rounds_by_idx.setdefault(idx, {"round": idx, "tool_calls": []})
            r["llm_request"] = data
        elif lt == "llm_response":
            idx = e.get("round") or 0
            r = rounds_by_idx.setdefault(idx, {"round": idx, "tool_calls": []})
            r["llm_response"] = data
        elif lt == "tool_call":
            idx = e.get("round") or 0
            r = rounds_by_idx.setdefault(idx, {"round": idx, "tool_calls": []})
            r["tool_calls"].append({"call": data, "result": None})
        elif lt == "tool_result":
            idx = e.get("round") or 0
            r = rounds_by_idx.setdefault(idx, {"round": idx, "tool_calls": []})
            for tc in reversed(r["tool_calls"]):
                if tc["result"] is None and tc["call"].get("tool_name") == data.get("tool_name"):
                    tc["result"] = data
                    break
        elif lt == "chat_response":
            out["chat_response"] = data
        elif lt == "error_snapshot":
            out["error"] = data

    out["rounds"] = [rounds_by_idx[k] for k in sorted(rounds_by_idx)]
    if not show_tools:
        for r in out["rounds"]:
            if "llm_request" in r and isinstance(r["llm_request"], dict):
                r["llm_request"].pop("tool_schemas", None)
    if not show_system_prompt and out["chat_request"]:
        out["chat_request"].pop("system_prompt", None)
    return out


@obs_router.get("/traces/{correlation_id}")
async def get_trace(
    correlation_id: str,
    show_tools: bool = Query(False),
    show_system_prompt: bool = Query(False),
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await reconstruct_trace(
        correlation_id, db=db, gcloud_reader=_gcloud_read,
        show_tools=show_tools, show_system_prompt=show_system_prompt
    )
    return {"data": data, "audit_id": None, "env": "server"}

"""Root admin router. Mounts subrouters under /api/v1/admin/*."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .auth import admin_auth_router
from .deps import AdminContext, audit_write, require_admin
from .observability import obs_router
from .subscriptions import sub_router
from .users import users_router

admin_router = APIRouter(prefix="/api/v1/admin")
admin_router.include_router(admin_auth_router)
admin_router.include_router(obs_router)
admin_router.include_router(users_router)
admin_router.include_router(sub_router)


class _PingBody(BaseModel):
    reason: str


@admin_router.post("/ping")
@audit_write(action="admin.ping", target_type=None)
async def admin_ping(
    body: _PingBody,
    ctx: AdminContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return {"pong": True, "admin": ctx.user.email}

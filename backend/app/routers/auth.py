import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user_id,
    verify_apple_token,
    verify_google_token,
    verify_token,
)
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    AuthRequest,
    AuthResponse,
    DevAuthRequest,
    RefreshRequest,
    RefreshResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _find_or_create_user(
    db: AsyncSession, email: str, name: str | None, provider: str
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            auth_provider=provider,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("user_created", extra={"user_id": str(user.id), "provider": provider})
    else:
        logger.info("user_login", extra={"user_id": str(user.id), "provider": provider})

    return user


def _make_tokens(user: User) -> AuthResponse:
    user_id = str(user.id)
    return AuthResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user_id=user_id,
    )


@router.post("/dev", response_model=AuthResponse)
async def login_dev(req: DevAuthRequest, db: AsyncSession = Depends(get_db)):
    """Dev-only login — no OAuth verification, just creates/finds user and returns tokens."""
    user = await _find_or_create_user(db, req.email, req.name, "dev")
    return _make_tokens(user)


@router.post("/apple", response_model=AuthResponse)
async def login_apple(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    info = await verify_apple_token(req.id_token)
    user = await _find_or_create_user(db, info["email"], info.get("name"), "apple")
    return _make_tokens(user)


@router.post("/google", response_model=AuthResponse)
async def login_google(req: AuthRequest, db: AsyncSession = Depends(get_db)):
    info = await verify_google_token(req.id_token)
    user = await _find_or_create_user(db, info["email"], info.get("name"), "google")
    return _make_tokens(user)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(req: RefreshRequest):
    payload = verify_token(req.refresh_token, "refresh")
    new_access = create_access_token(payload["sub"])
    return RefreshResponse(access_token=new_access)


@router.get("/me", response_model=UserResponse)
async def me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        auth_provider=user.auth_provider,
    )

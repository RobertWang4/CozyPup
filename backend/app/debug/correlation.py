"""Request correlation via ContextVar for tracking requests across the system."""

import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
pet_id_var: ContextVar[str] = ContextVar("pet_id", default="")


def generate_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_correlation_id(cid: str) -> None:
    correlation_id_var.set(cid)


def get_user_id() -> str:
    return user_id_var.get()


def set_user_id(uid: str) -> None:
    user_id_var.set(uid)


def get_pet_id() -> str:
    return pet_id_var.get()


def set_pet_id(pid: str) -> None:
    pet_id_var.set(pid)


def get_correlation_context() -> dict:
    return {
        "correlation_id": get_correlation_id(),
        "user_id": get_user_id(),
        "pet_id": get_pet_id(),
    }

"""Canonical tool metadata contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]
ToolValidator = Callable[[dict[str, Any]], str | None]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    validate: ToolValidator | None = None
    accepts_kwargs: bool = False
    read_only: bool = False
    destructive: bool = False
    requires_confirmation: bool = False
    concurrency_safe: bool = False
    search_hint: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "read_only": self.read_only,
            "destructive": self.destructive,
            "requires_confirmation": self.requires_confirmation,
            "concurrency_safe": self.concurrency_safe,
            "search_hint": self.search_hint,
            "tags": list(self.tags),
        }

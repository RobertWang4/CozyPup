"""Error hierarchy for PetPal debug system."""

import inspect
import os
from enum import Enum


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    AUTH = "auth"
    DATABASE = "db"
    AGENT_LLM = "agent_llm"
    EXTERNAL_API = "external_api"
    NETWORK = "network"
    UNKNOWN = "unknown"


class PetPalError(Exception):
    category = ErrorCategory.UNKNOWN

    def __init__(self, message: str, context: dict = None, module: str = None):
        super().__init__(message)
        self.module = module or self._infer_module()
        self.context = context or {}

    def _infer_module(self) -> str:
        """Walk the call stack to find the first frame outside this file."""
        this_file = os.path.abspath(__file__)
        for frame_info in inspect.stack():
            if os.path.abspath(frame_info.filename) != this_file:
                frame_module = frame_info.frame.f_globals.get("__name__", "")
                if frame_module:
                    return frame_module
                return frame_info.filename
        return "unknown"


class AgentError(PetPalError):
    category = ErrorCategory.AGENT_LLM


class DatabaseError(PetPalError):
    category = ErrorCategory.DATABASE


class ExternalAPIError(PetPalError):
    category = ErrorCategory.EXTERNAL_API


class AuthError(PetPalError):
    category = ErrorCategory.AUTH


class ValidationError(PetPalError):
    category = ErrorCategory.VALIDATION

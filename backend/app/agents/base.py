import logging
import time
from abc import ABC, abstractmethod

from app.debug.correlation import set_pet_id


class BaseAgent(ABC):
    """Base class for all PetPal agents. Subclass and implement _run()."""

    name: str  # Override in subclass, e.g. name = "record_agent"

    def __init__(self):
        self.logger = logging.getLogger(f"app.agents.{self.name}")

    async def execute(self, message: str, context: dict, **kwargs) -> dict:
        """Execute the agent with automatic logging. Do not override this."""
        start = time.monotonic()

        # Set pet_id in ContextVar if context contains it
        if "pet_id" in context:
            set_pet_id(str(context["pet_id"]))

        # Log agent start
        self.logger.debug(
            "agent_start",
            extra={"agent": self.name, "message_preview": message[:200], "context_keys": list(context.keys())},
        )

        try:
            result = await self._run(message, context, **kwargs)
            duration_ms = (time.monotonic() - start) * 1000

            # Log agent complete
            self.logger.info(
                "agent_complete",
                extra={
                    "agent": self.name,
                    "output_keys": list(result.keys()) if isinstance(result, dict) else [],
                    "duration_ms": round(duration_ms),
                },
            )
            return result

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000

            # Log agent error
            self.logger.error(
                "agent_error",
                extra={
                    "agent": self.name,
                    "duration_ms": round(duration_ms),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "message_preview": message[:200],
                },
                exc_info=True,
            )
            raise

    @abstractmethod
    async def _run(self, message: str, context: dict, **kwargs) -> dict:
        """Implement your agent logic here."""
        ...

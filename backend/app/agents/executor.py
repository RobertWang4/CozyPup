"""
Executor Agent: Independent sub-agent that executes a single tool.
- Receives minimal context (task description + relevant tool definitions)
- Non-streaming LLM call
- Returns structured JSON result
- Handles destructive operation confirm gate
"""
import json
import logging
from dataclasses import dataclass, field

import litellm

from app.agents import llm_extra_kwargs
from app.agents.locale import t
from app.config import settings
from app.agents.tools import TOOL_DEFINITIONS, execute_tool
from app.agents.validation import validate_tool_args

logger = logging.getLogger(__name__)

CONFIRM_TOOLS = {"delete_pet", "delete_calendar_event", "delete_reminder"}


@dataclass
class ExecutorResult:
    """Structured result from executor."""
    success: bool = False
    tool: str | None = None
    arguments: dict = field(default_factory=dict)
    card: dict | None = None
    summary: str = ""
    needs_confirm: bool = False
    description: str = ""
    error: str | None = None


async def run_executor(
    task_description: str,
    context: str,
    available_tools: list[str] | None = None,
    db=None,
    user_id=None,
    today: str = "",
    lang: str = "zh",
    **kwargs,
) -> ExecutorResult:
    """
    Run a single executor to complete one task.

    Args:
        task_description: What to do (e.g. "记录三妹吃狗粮")
        context: Relevant context (e.g. "三妹(id=abc, species=dog)")
        available_tools: Filter tool definitions to only these tools. None = all tools.
        db: Database session for tool execution
        user_id: User ID for ownership checks
        today: Today's date string (YYYY-MM-DD)
        lang: Language code for i18n ("zh" or "en")

    Returns:
        ExecutorResult with structured data
    """
    # Filter tools if specified
    if available_tools:
        tools = [td for td in TOOL_DEFINITIONS if td["function"]["name"] in available_tools]
    else:
        tools = TOOL_DEFINITIONS

    if not tools:
        return ExecutorResult(success=False, error="No matching tools available")

    # Build minimal messages
    user_content = f"{t('executor_date_label', lang)}: {today}\n\n{t('executor_task_label', lang)}: {task_description}"
    if context:
        user_content += f"\n\n{t('executor_context_label', lang)}: {context}"

    messages = [
        {"role": "system", "content": t("executor_system_prompt", lang)},
        {"role": "user", "content": user_content},
    ]

    try:
        # Non-streaming call (faster for short outputs)
        response = await litellm.acompletion(
            model=settings.executor_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
            stream=False,
            **llm_extra_kwargs(),
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls

        if not tool_calls:
            # LLM decided no tool needed
            return ExecutorResult(
                success=True,
                summary=message.content or t("executor_no_tool", lang),
            )

        # Process first tool call only
        tc = tool_calls[0]
        fn_name = tc.function.name

        try:
            fn_args = json.loads(tc.function.arguments)
        except json.JSONDecodeError as exc:
            return ExecutorResult(
                success=False,
                tool=fn_name,
                error=f"Invalid JSON arguments: {exc}",
            )

        # Validate
        errors = validate_tool_args(fn_name, fn_args)
        if errors:
            # Retry once with error feedback
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": fn_name, "arguments": tc.function.arguments}}
            ]})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({"error": "Validation failed: " + "; ".join(errors)}),
            })

            retry_response = await litellm.acompletion(
                model=settings.executor_model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
                stream=False,
                **llm_extra_kwargs(),
            )

            retry_msg = retry_response.choices[0].message
            if retry_msg.tool_calls:
                tc = retry_msg.tool_calls[0]
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    return ExecutorResult(success=False, tool=fn_name, error="JSON parse failed on retry")

                errors = validate_tool_args(fn_name, fn_args)
                if errors:
                    return ExecutorResult(
                        success=False,
                        tool=fn_name,
                        arguments=fn_args,
                        error="Validation failed after retry: " + "; ".join(errors),
                    )
            else:
                return ExecutorResult(
                    success=False,
                    error="LLM gave up after validation error",
                )

        # Confirm gate for destructive operations
        if fn_name in CONFIRM_TOOLS:
            return ExecutorResult(
                needs_confirm=True,
                tool=fn_name,
                arguments=fn_args,
                description=f"{t('executor_confirm', lang)}: {fn_name}",
            )

        # Execute tool
        if db is None or user_id is None:
            return ExecutorResult(
                success=False,
                tool=fn_name,
                arguments=fn_args,
                error="No database session or user_id provided",
            )

        result = await execute_tool(fn_name, fn_args, db, user_id, **kwargs)
        await db.commit()

        card = result.get("card")
        return ExecutorResult(
            success=True,
            tool=fn_name,
            arguments=fn_args,
            card=card,
            summary=f"{t('executor_done', lang)} {fn_name}",
        )

    except Exception as exc:
        logger.error("executor_error", extra={
            "task": task_description,
            "error": str(exc),
        })
        return ExecutorResult(
            success=False,
            error=str(exc),
        )

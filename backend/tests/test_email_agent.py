"""Tests for the Email Agent."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.email_agent import EmailAgent, _build_pet_context


def _make_pet(name="Buddy", species="dog", breed="Golden Retriever", birthday=None, weight=30.0):
    """Create a mock Pet object."""
    pet = MagicMock()
    pet.name = name
    pet.species.value = species
    pet.breed = breed
    pet.birthday = birthday or date(2020, 6, 15)
    pet.weight = weight
    return pet


def _make_litellm_response(content: str):
    """Build a mock LiteLLM completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


VALID_EMAIL_JSON = json.dumps({
    "subject": "Appointment Request - Buddy - Recurring Vomiting",
    "body": "Dear Dr. [___],\n\nI am writing to request an appointment for my Golden Retriever, Buddy.\n\nOver the past week, Buddy has experienced recurring vomiting episodes.\n\nI would appreciate your earliest available appointment.\n\nThank you,\n[Owner Name]",
})


@pytest.mark.asyncio
class TestEmailAgent:
    """Test EmailAgent with mocked LiteLLM."""

    @patch("app.agents.email_agent.litellm")
    async def test_returns_email_card_on_valid_response(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Help me write an email to the vet about Buddy's vomiting",
            {
                "pets": [_make_pet()],
                "context_messages": [
                    {"role": "user", "content": "Buddy has been vomiting for 3 days"},
                    {"role": "assistant", "content": "I'm sorry to hear that. Has Buddy been eating normally?"},
                ],
            },
        )

        assert result["response"] == "Here's a draft email for your vet:"
        assert result["card"]["type"] == "email"
        assert result["card"]["subject"] == "Appointment Request - Buddy - Recurring Vomiting"
        assert "Golden Retriever" in result["card"]["body"]
        assert "Dear Dr." in result["card"]["body"]

    @patch("app.agents.email_agent.litellm")
    async def test_card_format_has_required_fields(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Write an email to my vet",
            {"pets": [_make_pet()], "context_messages": []},
        )

        card = result["card"]
        assert "type" in card
        assert "subject" in card
        assert "body" in card
        assert card["type"] == "email"
        assert isinstance(card["subject"], str)
        assert isinstance(card["body"], str)

    @patch("app.agents.email_agent.litellm")
    async def test_handles_malformed_json_response(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response("This is not JSON at all, sorry!")
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Write an email to the vet",
            {"pets": [_make_pet()], "context_messages": []},
        )

        assert "trouble formatting" in result["response"]
        assert result["card"] is None

    @patch("app.agents.email_agent.litellm")
    async def test_handles_empty_body_in_response(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(json.dumps({"subject": "Test", "body": ""}))
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Write an email",
            {"pets": [_make_pet()], "context_messages": []},
        )

        assert "wasn't able to generate" in result["response"]
        assert result["card"] is None

    @patch("app.agents.email_agent.litellm")
    async def test_context_messages_included_in_llm_call(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        context_messages = [
            {"role": "user", "content": "Buddy threw up this morning"},
            {"role": "assistant", "content": "Was there any blood?"},
            {"role": "user", "content": "No blood, just food"},
        ]
        agent = EmailAgent()
        await agent.execute(
            "Email the vet about this",
            {"pets": [_make_pet()], "context_messages": context_messages},
        )

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]

        # System prompt + 3 context messages + 1 user message = 5
        assert len(messages) == 5
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "Buddy threw up this morning"}
        assert messages[2] == {"role": "assistant", "content": "Was there any blood?"}
        assert messages[3] == {"role": "user", "content": "No blood, just food"}
        assert messages[4] == {"role": "user", "content": "Email the vet about this"}

    @patch("app.agents.email_agent.litellm")
    async def test_limits_context_to_10_messages(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        context_messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        agent = EmailAgent()
        await agent.execute(
            "Write email",
            {"pets": [_make_pet()], "context_messages": context_messages},
        )

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]
        # 1 system + 10 context (last 10) + 1 current = 12
        assert len(messages) == 12

    @patch("app.agents.email_agent.litellm")
    async def test_works_with_no_pets(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Write an email to the vet",
            {"pets": [], "context_messages": []},
        )

        assert result["card"] is not None
        # Verify system prompt contains fallback text
        call_args = mock_litellm.acompletion.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "No pet information available" in system_msg

    @patch("app.agents.email_agent.litellm")
    async def test_handles_markdown_code_fences(self, mock_litellm):
        fenced = f"```json\n{VALID_EMAIL_JSON}\n```"
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(fenced)
        )
        agent = EmailAgent()
        result = await agent.execute(
            "Write email",
            {"pets": [_make_pet()], "context_messages": []},
        )

        assert result["card"] is not None
        assert result["card"]["type"] == "email"

    @patch("app.agents.email_agent.litellm")
    async def test_uses_cheap_model(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(
            return_value=_make_litellm_response(VALID_EMAIL_JSON)
        )
        agent = EmailAgent()
        await agent.execute(
            "Write email",
            {"pets": [_make_pet()], "context_messages": []},
        )

        call_args = mock_litellm.acompletion.call_args
        assert "cheap" in call_args.kwargs["model"] or "qwen" in call_args.kwargs["model"]


class TestBuildPetContext:
    """Test the pet context builder helper."""

    def test_empty_pets_list(self):
        assert _build_pet_context([]) == "No pet information available."

    def test_single_pet_full_info(self):
        pet = _make_pet()
        result = _build_pet_context([pet])
        assert "Buddy" in result
        assert "dog" in result
        assert "Golden Retriever" in result
        assert "30.0kg" in result
        assert "2020-06-15" in result

    def test_pet_without_optional_fields(self):
        pet = _make_pet(breed=None, birthday=None, weight=None)
        result = _build_pet_context([pet])
        assert "Buddy" in result
        assert "dog" in result
        assert "breed" not in result

    def test_multiple_pets(self):
        pets = [_make_pet(name="Buddy"), _make_pet(name="Luna", species="cat")]
        result = _build_pet_context(pets)
        assert "Buddy" in result
        assert "Luna" in result

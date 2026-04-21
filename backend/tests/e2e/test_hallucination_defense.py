"""E2E guard rails for the agent's write-operation fabrication defense.

Regression tests against the 2026-04-20 hallucination bug where grok-4-1-fast
claimed "已删除 / 已更新" without ever calling the write tool. The layered
defense (NUDGE restore, speak-before-tool relaxed for update/delete, thinking
SSE, write-claim nag, pushback preamble, fabrication guard, DB verification)
is validated here.

Run against live Cloud Run:
    E2E_BASE_URL=https://backend-601329501885.northamerica-northeast1.run.app \
        pytest tests/e2e/test_hallucination_defense.py -v -s
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.conftest import E2EClient, get_tools_called


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Phrases that indicate the assistant is claiming a completed write.
_WRITE_CLAIM = re.compile(
    r"已(?:更新|改为|改成|修改|删除|记录|保存|添加|创建|修正)"
    r"|(?:改好了|删掉了|记下了)"
    r"|\b(?:updated|changed|deleted|removed|recorded|saved|created|modified)\b",
    re.IGNORECASE,
)


def claims_write(text: str) -> bool:
    return bool(_WRITE_CLAIM.search(text or ""))


async def _seed_event(client: E2EClient, pet_id: str, title: str, date_str: str = "2026-04-20") -> dict:
    """Seed a calendar event directly via REST (bypasses LLM)."""
    resp = await client._client.post(
        f"{client.api}/calendar",
        headers=client.headers,
        json={
            "pet_id": pet_id,
            "event_date": date_str,
            "title": title,
            "type": "log",
            "category": "daily",
            "source": "manual",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def _list_events(client: E2EClient) -> list[dict]:
    # Covers the April 2026 window our seed dates live in.
    resp = await client._client.get(
        f"{client.api}/calendar",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
        headers=client.headers,
    )
    resp.raise_for_status()
    return resp.json()


async def _fresh_client_with_pet(base_url: str) -> tuple[E2EClient, dict]:
    c = E2EClient(base_url, debug=True)
    await c.auth_dev()
    # Seed a pet deterministically via chat so ownership is set up.
    r = await c.chat("我养了一只狗，叫维尼")
    pets = (await c._client.get(f"{c.api}/pets", headers=c.headers)).json()
    assert pets, "Pet creation failed in bootstrap"
    return c, pets[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_claim_backed_by_real_tool_call(base_url):
    """When user says '删掉 X', either a confirm card is shown OR the write
    tool actually executed. Reply text must not fabricate completion."""
    client, pet = await _fresh_client_with_pet(base_url)
    try:
        evt = await _seed_event(client, pet["id"], "出去玩")

        r = await client.chat("删掉今天出去玩那条")

        text = r.text
        has_confirm = r.has_card("confirm_action")
        has_deleted = r.has_card("event_deleted")

        if claims_write(text):
            # If text says "deleted", the action must have really happened
            # (either confirm card pending OR event_deleted card verified).
            assert has_confirm or has_deleted, (
                f"Fabrication: text claims write but no confirm/deleted card.\n"
                f"Text: {text!r}\n"
                f"Cards: {[c.get('type') for c in r.cards]}"
            )

        # If an event_deleted card fired, the DB row must be gone AND verified=True
        if has_deleted:
            card = r.first_card("event_deleted")
            assert card.get("verified") is True, f"Delete card missing verified flag: {card}"
            events = await _list_events(client)
            assert not any(e["id"] == evt["id"] for e in events), "DB still has the event after 'deleted' card"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_pushback_triggers_fresh_query(base_url):
    """After the LLM makes a delete claim, if the user says '你没删', the
    pushback preamble should inject and force a fresh query + real action."""
    client, pet = await _fresh_client_with_pet(base_url)
    try:
        await _seed_event(client, pet["id"], "出去玩")
        # First turn — the LLM may emit a confirm card or really delete
        r1 = await client.chat("删掉今天出去玩那条")
        # Pushback
        r2 = await client.chat("你没删，你好好再查一下")
        tools = get_tools_called(r2)

        # The pushback preamble must force at least a fresh query_calendar_events.
        # If the LLM just repeats "已删除" without any tools_called, the defense failed.
        assert tools, (
            f"Pushback did not trigger any tool call — LLM is still fabricating.\n"
            f"r2.text: {r2.text!r}\n"
            f"r2 cards: {[c.get('type') for c in r2.cards]}"
        )
        assert "query_calendar_events" in tools or any(t.startswith("delete") for t in tools), (
            f"Pushback should force a fresh query/delete; got {tools}"
        )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_fabrication_guard_replaces_lie_with_warning(base_url):
    """If after all nag rounds the LLM still fabricates (text claims write but
    no real write executed and no confirm pending), the fabrication guard
    must replace the text with an honest failure message + warning card."""
    client, pet = await _fresh_client_with_pet(base_url)
    try:
        # Don't seed any events — user asks to delete a nonexistent one.
        # The LLM may query and find nothing. If it then claims "已删除"
        # anyway, the guard should kick in.
        r = await client.chat("把我今天遛狗那条删掉")

        tools = get_tools_called(r)
        has_write_executed = any(t.startswith(("delete_", "update_")) for t in tools)
        has_confirm = r.has_card("confirm_action")
        has_warning = r.has_card("warning")

        # If the assistant's final text claims a write, it must be backed by
        # a real tool OR a confirm card OR a warning card must have fired.
        if claims_write(r.text):
            assert has_write_executed or has_confirm or has_warning, (
                f"No defense triggered despite write claim.\n"
                f"Text: {r.text!r}\n"
                f"Tools: {tools}\n"
                f"Cards: {[c.get('type') for c in r.cards]}"
            )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_update_rename_actually_writes(base_url):
    """User says '改成 X' — update must actually execute (or present a
    confirm), and DB must reflect the change after confirm/direct execution."""
    client, pet = await _fresh_client_with_pet(base_url)
    try:
        evt = await _seed_event(client, pet["id"], "Timmy来家玩")

        r = await client.chat("把 Timmy 来家玩 改成 Kimi 来家玩")
        tools = get_tools_called(r)
        has_confirm = r.has_card("confirm_action")
        has_record = r.has_card("record")

        # Must be backed by tooling activity
        if claims_write(r.text):
            assert has_confirm or has_record, (
                f"Update claim not backed by card.\n"
                f"Text: {r.text!r}\n"
                f"Cards: {[c.get('type') for c in r.cards]}"
            )

        # If LLM claims completion AND emitted a record card, DB title must match
        if has_record and "Kimi" in r.text:
            card = r.first_card("record")
            assert card.get("verified") is True, f"Record card missing verified: {card}"
            events = await _list_events(client)
            updated = next((e for e in events if e["id"] == evt["id"]), None)
            assert updated is not None, "Event disappeared"
            assert "Kimi" in updated["title"], f"DB title did not change: {updated['title']}"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_thinking_sse_fires_for_write_tools(base_url):
    """The server-side thinking SSE event must fire at least once when a
    write tool is invoked — this replaces the old 'speak before tool' rule."""
    client, pet = await _fresh_client_with_pet(base_url)
    try:
        await _seed_event(client, pet["id"], "出去玩")
        r = await client.chat("删掉今天出去玩那条")

        thinking_events = [e for e in r.raw_events if e.get("event") == "thinking"]
        assert thinking_events, (
            f"No thinking SSE event fired — user would stare at silence.\n"
            f"Events: {[e.get('event') for e in r.raw_events]}"
        )
    finally:
        await client.close()

import asyncio
import time
from dataclasses import replace

import pytest
from app.agent import Agent
from app.browser import DEMO_URL, BrowserBoundaryError
from app.config import settings
from app.schemas import TurnRequest


class FakeBrowser:
    def __init__(self):
        self.reads = 0
        self.pages = {}
        self.closed = []

    async def navigate(self, sid, url):
        self.pages[sid] = {"url": url, "revision": 1}
        return dict(self.pages[sid])

    async def read(self, sid, url, revision):
        if self.pages[sid] != {"url": url, "revision": revision}:
            raise BrowserBoundaryError("The page changed. Request new permission.")
        await asyncio.sleep(0)
        self.reads += 1
        return "Community garden opens. Library extends evening hours."

    async def close_session(self, sid):
        self.closed.append(sid)
        self.pages.pop(sid, None)


class FakeModel:
    async def extract(self, *args):
        return {}

    async def draft(self, *args):
        return None

    async def summarize(self, *args):
        return None


@pytest.fixture
def agent():
    return Agent(replace(settings, llm_enabled=False), FakeBrowser(), FakeModel())


def req(text="", sid="test", token=None, decision=None):
    return TurnRequest(
        session_id=sid,
        text=text,
        pending_interrupt_id=token,
        user_permission_granted=decision,
    )


async def open_page(agent, sid="test"):
    return await agent.turn(req("Open the demo page", sid))


async def test_email_remembers_recipient_and_requires_topic_and_timeline(agent):
    first = await agent.turn(req("Draft an email to Sarah"))
    assert first.status == "CLARIFICATION_NEEDED"
    assert first.data["recipient"] == "Sarah"
    assert first.data["missing_slot"] == "topic"
    second = await agent.turn(req("The project launch", token=first.interrupt_id))
    assert second.data["missing_slot"] == "timeline"
    assert second.data["recipient"] == "Sarah"
    third = await agent.turn(req("Next Friday", token=second.interrupt_id))
    assert third.action_type == "DRAFT_CREATED"
    assert "Sarah" in third.data["draft_content"]
    assert "project launch" in third.data["draft_content"]
    assert "Next Friday" in third.data["draft_content"]
    assert agent.sessions["test"].kind is None


async def test_complete_email_in_one_turn(agent):
    result = await agent.turn(req("Draft an email to Sarah about the launch by Friday"))
    assert result.action_type == "DRAFT_CREATED"


async def test_stale_clarification_does_not_overwrite_slots(agent):
    first = await agent.turn(req("Draft an email to Sarah"))
    second = await agent.turn(req("A launch", token=first.interrupt_id))
    stale = await agent.turn(req("A launch", token=first.interrupt_id))
    assert stale.interrupt_id == second.interrupt_id
    assert "timeline" not in agent.sessions["test"].slots


async def test_navigation_never_reads(agent):
    gate = await open_page(agent)
    assert gate.status == "PERMISSION_REQUIRED"
    assert gate.data["url"] == DEMO_URL
    assert not gate.data["dom_read"]
    assert agent.browser.reads == 0


@pytest.mark.parametrize(
    "decision,text", [(False, ""), (None, "Deny"), (None, "don't read")]
)
async def test_denial_never_reads(agent, decision, text):
    gate = await open_page(agent)
    result = await agent.turn(req(text, token=gate.interrupt_id, decision=decision))
    assert result.action_type == "PERMISSION_DENIED"
    assert agent.browser.reads == 0
    assert agent.sessions["test"].consent is None


@pytest.mark.parametrize("text", ["allow", "yes", "Allow.", "go ahead"])
async def test_exact_spoken_approval_reads_once(agent, text):
    gate = await open_page(agent)
    result = await agent.turn(req(text, token=gate.interrupt_id))
    assert result.action_type == "BROWSER_SUMMARIZED"
    assert agent.browser.reads == 1
    replay = await agent.turn(req(text, token=gate.interrupt_id))
    assert replay.action_type == "NO_PENDING_PERMISSION"
    assert agent.browser.reads == 1


@pytest.mark.parametrize(
    "text",
    [
        "I don't allow that",
        "not yes",
        "maybe",
        "allow but not yet",
        "yes no",
        "allow123",
        "a!l!l!o!w",
    ],
)
async def test_ambiguous_or_negative_text_cannot_grant(agent, text):
    gate = await open_page(agent)
    result = await agent.turn(req(text, token=gate.interrupt_id))
    assert result.status == "PERMISSION_REQUIRED"
    assert agent.browser.reads == 0


async def test_wrong_token_cannot_grant(agent):
    gate = await open_page(agent)
    result = await agent.turn(req("Allow", token="wrong", decision=True))
    assert result.interrupt_id == gate.interrupt_id
    assert agent.browser.reads == 0


async def test_cross_session_token_cannot_grant(agent):
    first = await open_page(agent, "one")
    second = await open_page(agent, "two")
    result = await agent.turn(req("Allow", "two", first.interrupt_id, True))
    assert result.interrupt_id == second.interrupt_id
    assert agent.browser.reads == 0


async def test_expired_consent_never_reads(agent):
    gate = await open_page(agent)
    agent.sessions["test"].consent.expires = time.monotonic() - 1
    result = await agent.turn(req("Allow", token=gate.interrupt_id, decision=True))
    assert result.action_type == "PERMISSION_EXPIRED"
    assert agent.browser.reads == 0


async def test_navigation_invalidates_consent(agent):
    gate = await open_page(agent)
    agent.browser.pages["test"]["revision"] += 1
    result = await agent.turn(req("Allow", token=gate.interrupt_id, decision=True))
    assert result.action_type == "PAGE_CHANGED"
    assert agent.browser.reads == 0


async def test_concurrent_approval_only_reads_once(agent):
    gate = await open_page(agent)
    responses = await asyncio.gather(
        *[
            agent.turn(req("Allow", token=gate.interrupt_id, decision=True))
            for _ in range(2)
        ]
    )
    assert sorted(r.action_type for r in responses) == [
        "BROWSER_SUMMARIZED",
        "NO_PENDING_PERMISSION",
    ]
    assert agent.browser.reads == 1


async def test_cancel_clears_draft_and_gate(agent):
    await open_page(agent)
    result = await agent.turn(req("Cancel"))
    assert result.action_type == "CANCELLED"
    assert agent.browser.reads == 0
    assert agent.sessions["test"].consent is None


async def test_expiry_cleanup(agent):
    await open_page(agent)
    agent.sessions["test"].consent.expires = time.monotonic() - 1
    await agent.reap()
    assert agent.sessions["test"].consent is None
    assert agent.browser.reads == 0
    assert "test" in agent.browser.closed


async def test_meeting_clarification(agent):
    response = await agent.turn(req("Prepare a meeting with Alex"))
    for answer, missing in [
        ("The launch", "topic"),
        ("Tomorrow", "date"),
        ("2pm Arizona time", "time"),
    ]:
        assert response.data["missing_slot"] == missing
        response = await agent.turn(req(answer, token=response.interrupt_id))
    assert response.action_type == "DRAFT_CREATED"
    assert response.data["kind"] == "meeting"


async def test_browser_error_is_recoverable(agent):
    async def broken(*_):
        raise BrowserBoundaryError("Address blocked.")

    agent.browser.navigate = broken
    result = await open_page(agent)
    assert result.status == "ERROR"
    assert not agent.sessions["test"].consent

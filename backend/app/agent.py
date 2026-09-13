import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import TypedDict
from urllib.parse import quote_plus

from langgraph.graph import END, START, StateGraph

from .browser import DEMO_URL, BrowserBoundaryError
from .schemas import TurnRequest, TurnResponse

ALLOW = {
    "allow",
    "yes",
    "yes please",
    "i allow",
    "allow once",
    "allow reading",
    "yes allow",
    "yes you may",
    "go ahead",
}
DENY = {"deny", "no", "no thanks", "do not read", "dont read", "cancel", "stop"}
QUESTIONS = {
    "recipient": "Who is this for?",
    "topic": "What should it be about?",
    "timeline": "What timeline or deadline should I mention? You can say “no deadline”.",
    "date": "What date should I propose for the meeting?",
    "time": "What time should I propose? Please include the time zone.",
}


def normalized(text):
    return " ".join(
        text.lower().replace("’", "'").replace("'", "").strip(" .!?,;:").split()
    )


def reply(status, speech, action, data=None, interrupt=None):
    return TurnResponse(
        status=status,
        speech_to_say=speech,
        action_type=action,
        data=data or {},
        interrupt_id=interrupt,
    )


@dataclass
class Consent:
    id: str
    url: str
    revision: int
    expires: float


@dataclass
class Session:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    kind: str | None = None
    slots: dict = field(default_factory=dict)
    missing: str | None = None
    clarification_id: str | None = None
    consent: Consent | None = None
    touched: float = field(default_factory=time.monotonic)
    audit: list = field(default_factory=list)

    def event(self, name):
        self.audit.append({"event": name, "at": time.time()})
        self.audit = self.audit[-60:]

    def reset(self):
        self.kind, self.missing, self.clarification_id, self.consent = (
            None,
            None,
            None,
            None,
        )
        self.slots = {}


class GraphState(TypedDict, total=False):
    request: TurnRequest
    session: Session
    route: str
    response: TurnResponse


class Agent:
    def __init__(self, settings, browser, model):
        self.settings, self.browser, self.model = settings, browser, model
        self.sessions: dict[str, Session] = {}
        graph = StateGraph(GraphState)
        graph.add_node("route_turn", self.route)
        for name in ["permission", "cancel", "draft", "browse", "help"]:
            graph.add_node(name, getattr(self, name))
            graph.add_edge(name, END)
        graph.add_edge(START, "route_turn")
        graph.add_conditional_edges("route_turn", lambda state: state["route"])
        self.graph = graph.compile()

    async def turn(self, request):
        if request.session_id not in self.sessions:
            if len(self.sessions) >= self.settings.max_sessions:
                return reply(
                    "ERROR",
                    "Too many active sessions. Please try again later.",
                    "SESSION_LIMIT",
                )
            self.sessions[request.session_id] = Session()
        session = self.sessions[request.session_id]
        async with session.lock:
            session.touched = time.monotonic()
            result = await self.graph.ainvoke({"request": request, "session": session})
            response = result["response"]
            response.data["audit"] = list(session.audit)
            return response

    async def reap(self):
        for sid, session in list(self.sessions.items()):
            if session.lock.locked():
                continue
            async with session.lock:
                if session.consent and session.consent.expires <= time.monotonic():
                    session.consent = None
                    session.event("permission_expired")
                    await self.browser.close_session(sid)
                if time.monotonic() - session.touched > self.settings.session_ttl:
                    await self.browser.close_session(sid)
                    self.sessions.pop(sid, None)

    def route(self, state):
        req, session = state["request"], state["session"]
        text = req.text.strip().lower()
        if normalized(text) in {"cancel", "stop", "start over", "reset"}:
            route = "cancel"
        elif (
            session.consent
            or req.user_permission_granted is not None
            or normalized(text) in ALLOW | DENY
        ):
            route = "permission"
        elif session.kind:
            route = "draft"
        elif re.search(r"\b(email|draft|meeting|schedule|message)\b", text):
            session.kind = (
                "meeting" if re.search(r"\b(meeting|schedule)\b", text) else "email"
            )
            route = "draft"
        elif re.search(
            r"https?://|\b(open|browse|search|website|summarize|hacker news|demo page)\b",
            text,
        ):
            route = "browse"
        else:
            route = "help"
        return {"route": route}

    async def cancel(self, state):
        state["session"].reset()
        state["session"].event("task_cancelled")
        await self.browser.close_session(state["request"].session_id)
        return {
            "response": reply(
                "COMPLETE", "Cancelled. Ready for a new task.", "CANCELLED"
            )
        }

    def help(self, state):
        return {
            "response": reply(
                "COMPLETE",
                "I can draft an email, prepare a meeting proposal, or open a website and ask before reading it. What would you like to do?",
                "READY",
            )
        }

    async def draft(self, state):
        req, session = state["request"], state["session"]
        if (
            session.clarification_id
            and req.pending_interrupt_id != session.clarification_id
        ):
            return {
                "response": reply(
                    "CLARIFICATION_NEEDED",
                    QUESTIONS[session.missing],
                    "SLOT_FILLING",
                    {
                        **session.slots,
                        "missing_slot": session.missing,
                        "kind": session.kind,
                    },
                    session.clarification_id,
                )
            }
        text = req.text.strip()
        required = (
            ["recipient", "topic", "timeline"]
            if session.kind == "email"
            else ["recipient", "topic", "date", "time"]
        )
        extracted = {}
        # Fast paths make the scripted clarification loop immediate and work offline.
        recipient = re.search(
            r"\b(?:to|with)\s+(.+?)(?=\s+(?:about|regarding|on|by|for|tomorrow|today|next)\b|[,.!?]|$)",
            text,
            re.IGNORECASE,
        )
        if recipient:
            extracted["recipient"] = recipient.group(1).strip()
        topic = re.search(
            r"\b(?:about|regarding)\s+(.+?)(?=\s+(?:by|before)\b|$)",
            text,
            re.IGNORECASE,
        )
        if topic:
            extracted["topic"] = topic.group(1).strip(" .")
        deadline = re.search(r"\b(?:by|before)\s+(.+)", text, re.IGNORECASE)
        if deadline and session.kind == "email":
            extracted["timeline"] = deadline.group(1).strip(" .")
        if session.missing:
            # A free-form answer fills precisely the question we just asked.
            extracted.setdefault(session.missing, text)
        elif not extracted:
            extracted.update(
                await self.model.extract(text, session.kind, session.slots)
            )
        session.slots.update(
            {k: v for k, v in extracted.items() if k in required and v}
        )
        missing = next((k for k in required if not session.slots.get(k)), None)
        if missing:
            session.missing = missing
            session.clarification_id = "int_" + uuid.uuid4().hex
            session.event("clarification_requested")
            return {
                "response": reply(
                    "CLARIFICATION_NEEDED",
                    QUESTIONS[missing],
                    "SLOT_FILLING",
                    {**session.slots, "missing_slot": missing, "kind": session.kind},
                    session.clarification_id,
                )
            }
        slots, kind = dict(session.slots), session.kind
        draft = await self.model.draft(kind, slots)
        engine = "ollama" if draft else "template"
        if not draft:
            if kind == "email":
                timeline = (
                    "No deadline is specified."
                    if normalized(slots["timeline"])
                    in {"no deadline", "none", "no timeline"}
                    else f"The timeline is {slots['timeline']}."
                )
                draft = f"Subject: {slots['topic']}\n\nHi {slots['recipient']},\n\nI'm writing about {slots['topic']}. {timeline}\n\nPlease let me know your thoughts.\n\nBest regards"
            else:
                draft = f"Meeting proposal: {slots['topic']}\nWith: {slots['recipient']}\nDate: {slots['date']}\nTime: {slots['time']}\n\nPlease confirm whether this works for you."
        session.reset()
        session.event("draft_created")
        return {
            "response": reply(
                "COMPLETE",
                "Your draft is ready to review. Nothing has been sent or scheduled.",
                "DRAFT_CREATED",
                {
                    "draft_content": draft,
                    "slots": slots,
                    "kind": kind,
                    "engine": engine,
                },
            )
        }

    async def browse(self, state):
        req, session = state["request"], state["session"]
        text = req.text.strip()
        match = re.search(r'https?://[^\s<>"\']+', text)
        if match:
            url = match.group(0).rstrip(".,!?")
        elif "demo" in text.lower():
            url = DEMO_URL
        elif "hacker news" in text.lower():
            url = "https://news.ycombinator.com"
        else:
            domain = re.search(
                r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?", text, re.IGNORECASE
            )
            query = re.sub(
                r"^(?:search(?:\s+for)?|browse|open|summarize)\s+",
                "",
                text,
                flags=re.IGNORECASE,
            )
            url = (
                "https://" + domain.group(0)
                if domain
                else "https://www.google.com/search?q=" + quote_plus(query)
            )
        session.event("navigation_started")
        try:
            location = await self.browser.navigate(req.session_id, url)
        except BrowserBoundaryError as exc:
            return {"response": reply("ERROR", str(exc), "BROWSER_ERROR")}
        except Exception:
            return {
                "response": reply(
                    "ERROR",
                    "The browser could not open that page. Check the address, your connection, and the Playwright Chromium installation.",
                    "BROWSER_ERROR",
                )
            }
        session.event("navigation_completed_no_dom_read")
        session.consent = Consent(
            "int_" + uuid.uuid4().hex,
            location["url"],
            location["revision"],
            time.monotonic() + self.settings.permission_ttl,
        )
        session.event("permission_requested")
        return {"response": self.permission_prompt(session)}

    def permission_prompt(self, session):
        consent = session.consent
        return reply(
            "PERMISSION_REQUIRED",
            "The website is open. May I read the visible page text to summarize it? Say allow or deny.",
            "BROWSER_READ_GATE",
            {
                "url": consent.url,
                "target": "DOM_TEXT",
                "max_characters": self.settings.max_page_chars,
                "expires_at": time.time() + max(0, consent.expires - time.monotonic()),
                "dom_read": False,
            },
            consent.id,
        )

    async def permission(self, state):
        req, session = state["request"], state["session"]
        consent = session.consent
        if not consent:
            return {
                "response": reply(
                    "ERROR",
                    "There is no active read permission request. Open a website to begin.",
                    "NO_PENDING_PERMISSION",
                )
            }
        if consent.expires <= time.monotonic():
            session.consent = None
            session.event("permission_expired")
            await self.browser.close_session(req.session_id)
            return {
                "response": reply(
                    "COMPLETE",
                    "Permission expired. No page text was read. Open the website again to retry.",
                    "PERMISSION_EXPIRED",
                )
            }
        if req.pending_interrupt_id != consent.id:
            # A stale or cross-session token can never approve a current page.
            return {"response": self.permission_prompt(session)}
        decision = req.user_permission_granted
        if decision is None:
            words = normalized(req.text)
            decision = True if words in ALLOW else False if words in DENY else None
        if decision is None:
            return {"response": self.permission_prompt(session)}
        session.consent = (
            None  # Consume before awaiting: one consent permits one extraction.
        )
        if decision is False:
            session.event("permission_denied")
            await self.browser.close_session(req.session_id)
            return {
                "response": reply(
                    "COMPLETE",
                    "Permission denied. No page text was read.",
                    "PERMISSION_DENIED",
                    {"dom_read": False},
                )
            }
        session.event("permission_granted")
        try:
            content = await self.browser.read(
                req.session_id, consent.url, consent.revision
            )
        except BrowserBoundaryError as exc:
            session.event("read_blocked_page_changed")
            return {
                "response": reply(
                    "ERROR", str(exc), "PAGE_CHANGED", {"dom_read": False}
                )
            }
        except Exception:
            return {
                "response": reply(
                    "ERROR",
                    "The page could not be read. Open it again to request fresh permission.",
                    "BROWSER_ERROR",
                )
            }
        session.event("dom_read_completed")
        summary = await self.model.summarize(content) if content.strip() else None
        engine = "ollama" if summary else "excerpt"
        summary = summary or (
            content[:1200].strip()
            if content.strip()
            else "The page contained no readable visible text."
        )
        return {
            "response": reply(
                "COMPLETE",
                summary,
                "BROWSER_SUMMARIZED",
                {
                    "url": consent.url,
                    "summary": summary,
                    "engine": engine,
                    "characters_read": len(content),
                    "dom_read": True,
                },
            )
        }

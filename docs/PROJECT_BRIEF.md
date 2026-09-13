# Project Brief & Execution Spec: Local Voice Agent with Permission-Gated Automation

## 1. Executive Summary

A 100% open-source, locally run desktop voice assistant that executes natural voice dictation, resolves ambiguities via proactive slot-filling, controls a visible browser to complete tasks, and enforces a strict human-in-the-loop permission gate before reading or extracting on-screen data.

* **Core Value:** Local privacy, zero cloud API fees, multimodal desktop-to-browser control, and zero unprompted data scraping.
* **Primary Target:** A 2-hour rapid demo capable of executing scripted slot-filling and gated web navigation.

---

## 2. Technical Stack

| Layer | Technology | Function |
| --- | --- | --- |
| **Client Shell** | React (Vite) + Web Speech API (Optionally wrapped in Electron) | Voice transcription (`webkitSpeechRecognition`), speech synthesis (`speechSynthesis`), and modal state rendering. |
| **Agent Orchestrator** | Python FastAPI + LangGraph | Turn state management, interrupt handling, and conversational routing. |
| **Local LLM Engine** | Ollama (`llama3.2:3b` or `qwen2.5:7b`) | Slot-filling, intent extraction, and response summarization running strictly on local hardware. |
| **Browser Driver** | Playwright (`headless: false`) | Visible Chromium automation to visually demonstrate agent navigation and bounded DOM access. |

---

## 3. Core Operational Flows

### A. Dynamic Slot-Filling (Clarification Loop)

```
User Input ──► LLM Intent Check ──► Missing Required Slots?
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   ▼ (Yes)                                       ▼ (No)
        Status: CLARIFICATION_NEEDED                       Status: COMPLETE
     Prompt user for missing details                     Execute action / Save draft

```

### B. Bounded Human-in-the-Loop Gate (Browser Inspection)

```
User Voice Command ──► Playwright Opens Target URL (headless: false)
                                     │
                                     ▼
                   [Hard Stop at DOM Access Boundary]
             Emit Status: PERMISSION_REQUIRED & Voice Prompt
                                     │
                   ┌─────────────────┴─────────────────┐
                   ▼ (User Confirms: "Allow")          ▼ (User Denies / Timeout)
           Extract DOM & Summarize                   Halt Action & Clear Interrupt

```

---

## 4. Shared API Contract (`POST /agent/turn`)

All components and external agents interact over `http://localhost:8000/agent/turn`.

### Request Schema

```json
{
  "session_id": "string",
  "text": "string",
  "pending_interrupt_id": "string | null",
  "user_permission_granted": "boolean | null"
}

```

### Response Schemas by State

**1. Clarification Required (`CLARIFICATION_NEEDED`)**

```json
{
  "status": "CLARIFICATION_NEEDED",
  "interrupt_id": "int_101",
  "speech_to_say": "What date should I schedule the meeting for?",
  "action_type": "SLOT_FILLING",
  "data": { "recipient": "Alex" }
}

```

**2. Human-in-the-Loop Permission Required (`PERMISSION_REQUIRED`)**

```json
{
  "status": "PERMISSION_REQUIRED",
  "interrupt_id": "int_102",
  "speech_to_say": "I have navigated to the website. May I have permission to read the screen?",
  "action_type": "BROWSER_READ_GATE",
  "data": {
    "url": "https://news.ycombinator.com",
    "target": "DOM_TEXT"
  }
}

```

**3. Action Completed (`COMPLETE`)**

```json
{
  "status": "COMPLETE",
  "interrupt_id": null,
  "speech_to_say": "The draft has been finalized.",
  "action_type": "DRAFT_CREATED",
  "data": { "draft_content": "..." }
}

```

---

## 5. Execution Roadmap: What Gets Built First

To ship a functional prototype within 2 hours or across distributed agents, implement sequentially:

```
[Phase 1: Backend Foundation] ──► [Phase 2: Headful Browser] ──► [Phase 3: Web Speech UI] ──► [Phase 4: Wire & Demo]
         (0:00 - 0:30)                    (0:30 - 0:50)                  (0:50 - 1:25)               (1:25 - 2:00)

```

### Phase 1: Local Model & Server Foundation (Minutes 0:00 – 0:30)

* Stand up Ollama with a fast model (`llama3.2:3b` recommended for near-instant latency).
* Implement the FastAPI endpoint (`POST /agent/turn`) to accept JSON and parse missing parameters.
* Test slot-filling output using curl/Postman to ensure JSON validity.

### Phase 2: Browser Automation & Hard Interrupt Gate (Minutes 0:30 – 0:50)

* Instantiate Playwright with `headless: False`.
* Implement the navigation tool: open target page and **halt**.
* Ensure the function returns `PERMISSION_REQUIRED` without touching `page.inner_text()` until a second payload arrives with `user_permission_granted: True`.

### Phase 3: Client Interface & Speech Hooks (Minutes 0:50 – 1:25)

* Deploy a lightweight Vite React web shell (or Electron wrapper) exposing:
* Speech recognition hook (`webkitSpeechRecognition`) bound to microphone input.
* Speech synthesis voice feedback (`SpeechSynthesisUtterance`).
* Explicit visual modal for permission grants (Allow / Deny buttons).
* Text-input fallback box to mitigate noisy live mic conditions.



### Phase 4: Integration, Rehearsal & Verification (Minutes 1:25 – 2:00)

* Validate Script 1: Multi-turn slot-filling (Email/Draft).
* Validate Script 2: Launch browser -> Pause at consent gate -> User says "Allow" -> Scrape & speak summary.

---

## 6. Demo Acceptance Criteria

1. **Voice In / Voice Out:** The user speaks naturally; the system answers back with audible speech within 1.5 seconds.
2. **Context Memory:** Asking *"Draft an email to Sarah"* causes the system to stop and ask for the missing topic and timeline before generating output.
3. **Headful Proof-of-Action:** When commanded to search or browse, a visible Chromium window opens automatically on the desktop.
4. **Safety Barrier Verification:** The agent explicitly refuses to inspect the page DOM until permission is verified via the UI button or spoken affirmative command.
# Three-minute demo rehearsal

## Before presenting

- Run `ollama serve` if it is not already running.
- Start `.venv/bin/python scripts/dev.py`, then open `http://127.0.0.1:5173`.
- Check the green connection badge. On a wide window, the session panel should show `llama3.2:3b`, local Whisper, and visible Chromium.
- Run `.venv/bin/python scripts/smoke.py` once to warm the model and validate both flows. This opens a browser using only the included fictional demo page.
- Use text input if the room is noisy. The mic records until clicked again (55-second maximum).

## 0:00 — The promise

“Forma is a voice assistant running on this laptop. It helps with drafts and browsing, and asks before reading a page.”

## 0:20 — Clarification and memory

Say “Draft an email to Sarah.” Answer “The project launch.” Answer “Next Friday.”

Show that Sarah is remembered across turns and the draft is available to copy/download. Explain that no email is sent.

## 1:20 — The hard boundary

Say “Open the demo page.” Show the separate Chromium window. Return to Forma.

Explain that navigation has completed, but the agent has not extracted page text. The consent dialog identifies the exact URL, a 12,000-character limit, and an expiry.

Deny first. The task stops without reading. Repeat the request, then Allow once (button or voice). The local model summarizes the three fictional stories.

## 2:30 — Why it matters

Show the activity trail: navigation → permission requested → permission granted → DOM read. Every new page read needs a new approval. Consent cannot be reused or transferred to another session.

## Honest answers for judges

- The backend routes through LangGraph; Ollama never controls the authorization decision.
- Ollama and whisper.cpp run locally. Web Speech output uses a local installed voice. Optional browser speech input is allowed only in on-device mode.
- Public websites require network access; the demo page does not.
- A spoken acknowledgement starts immediately; final local generations take a few seconds on this machine. The 1.5-second end-to-end result target is not achieved.
- Email/calendar delivery, arbitrary app clicking, screenshots, and Electron packaging are outside this prototype.
- App source is MIT-licensed. Dependencies, model weights, and system speech voices retain their upstream licenses; the entire stack is not represented as OSI-approved open source.

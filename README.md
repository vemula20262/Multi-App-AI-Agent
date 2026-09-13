# Multi-App-AI-Agent
For the hackathon 

## Forma — local voice agent

A working hackathon prototype: speak or type a task, fill in missing details, and approve each browser read. Built with React + Vite, FastAPI + LangGraph, Ollama, Playwright, and whisper.cpp.

### Start on this Mac

```bash
# Terminal 1 (only if Ollama is not already running)
ollama serve

# Terminal 2, from this repository
.venv/bin/python scripts/dev.py
```

Open **http://127.0.0.1:5173**. Backend API docs: **http://127.0.0.1:8000/docs**.

### Install on a fresh machine

Requires Python 3.11–3.13, Node.js 22+, and a graphical desktop. macOS Apple Silicon is the verified demo environment. Allow roughly 3 GB for models/browser plus dependencies.

```bash
./scripts/setup.sh
# Install Ollama and whisper.cpp. This script supports Homebrew on macOS.
# If it asks you to start Ollama, run `ollama serve` in another terminal and rerun it.
./scripts/setup-local-models.sh
.venv/bin/python scripts/dev.py
```

On Linux/Windows, install [Ollama](https://ollama.com/download) and build/install [whisper.cpp](https://github.com/ggml-org/whisper.cpp), make `whisper-cli` available on PATH, then download the model using the model setup script. Linux may need `python -m playwright install --with-deps chromium`. Windows users can use Git Bash for setup scripts and set `WHISPER_BIN` as needed. These platforms have not been rehearsed here.

### Two demo scripts

1. Click **Draft an email**, or say **“Draft an email to Sarah.”**
2. Answer **“The project launch.”**
3. Answer **“Next Friday.”**
4. Review, copy, or download the draft. Nothing is sent.

Then:

1. Say **“Open the demo page and summarize it”**, or click **Explore a website**.
2. A separate **visible Chromium window** opens. Return to Forma to see the permission dialog. Page content has not been read.
3. Click **Deny access** and verify the activity trail. No extraction occurs.
4. Open the demo page again and click **Allow once**, or record **“Allow.”**
5. Read/hear the local summary. Reusing that approval cannot read again.

You can also say **“Open Hacker News”** or provide a public `https://` URL. The built-in page uses fictional content to make rehearsals reliable. “Prepare a meeting with Alex” demonstrates additional date/time clarification. Meeting output is a proposal, never a calendar write.

### Voice and privacy

- **Default voice input:** the browser records microphone audio, converts it to mono 16 kHz WAV, and sends it only to the localhost backend. whisper.cpp transcribes on this machine. Click the microphone again to stop; recordings stop automatically after 55 seconds.
- **Optional Web Speech input:** on-device recognition only (`processLocally = true`). If the browser or language pack cannot support that, the app displays an error; it never silently falls back to cloud recognition.
- **Voice output:** Web Speech synthesis using an installed English voice with `localService = true`. If no local voice is available, text remains visible.
- **Local generation:** Ollama `llama3.2:3b`. If unavailable or timed out, the UI labels template drafts and page excerpts accurately.
- **Network:** opening public sites still contacts those sites. Initial package/model setup requires downloads. No cloud LLM/STT API keys are used. No external fonts or analytics are loaded by the frontend.
- Sessions, slot values, and audit events stay in backend memory for up to an hour. Drafts in the UI remain until reload. Audio is processed in a temporary directory and removed after transcription. Models remain on disk. No personal browser profile is reused.

### Permission boundary

`POST /agent/turn` preserves the brief’s shared request and response contract:

```json
{"session_id":"demo-1","text":"Open the demo page","pending_interrupt_id":null,"user_permission_granted":null}
```

The returned `PERMISSION_REQUIRED` response includes an unpredictable `interrupt_id`, exact final URL, character limit, and expiry. A second request must supply the **same session and interrupt** plus `user_permission_granted: true` or an exact affirmative phrase such as `Allow`. Negative, ambiguous, missing, stale, cross-session, and expired approvals cannot read. Per-session locks serialize concurrent turns. Permission is consumed before reading. Navigation revision + URL checks invalidate consent when the page changes. Consent lasts 60 seconds by default; the cleanup loop closes expired tabs within five seconds.

`backend/app/browser.py` contains the sole DOM extraction call. It excludes form input values, editable regions, scripts, and hidden content, and caps text at 12,000 characters. Navigation reads no DOM, titles, screenshots, or response bodies. Cross-origin browser requests to the local API are rejected; private network destinations are blocked except the exact built-in demo URL. This is a single-user localhost prototype, not an authenticated multi-user service or hardened adversarial browsing sandbox.

### Development and verification

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
# With the app running (opens visible Chromium):
.venv/bin/python scripts/smoke.py
```

The graph explicitly routes through permission, cancellation, slot filling, browsing, and help nodes. The server owns authorization; the model cannot grant permissions or execute browser tools.

Configuration is documented in `.env.example`. The launcher uses exported environment variables; to load a file directly run `uvicorn app.main:app --app-dir backend --env-file .env --host 127.0.0.1 --port 8000` using the project virtualenv. `AGENT_LLM_ENABLED=false` enables deterministic rehearsal. `BROWSER_HEADLESS=true` is for automated tests only. Run **one backend worker** because session and browser state are in memory.

### Scope and honest limits

This version supports drafting, meeting proposals, public web navigation/search, and consent-gated text summaries. It does not send mail, write calendars, click through arbitrary application workflows, read screenshots, or control native apps. Local inference and speech speed depend on hardware and cold starts; the brief’s 1.5-second end-to-end voice target is not guaranteed. Text clarification uses a fast path. First model generation and microphone permission prompts can take longer.

Sources for implementation behavior: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api), [Ollama chat API](https://docs.ollama.com/api/chat), [Playwright Python](https://playwright.dev/python/docs/library), and [MDN on-device recognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/processLocally).

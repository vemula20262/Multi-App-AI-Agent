import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  AudioLines,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Copy,
  Download,
  FileText,
  Globe2,
  Headphones,
  Laptop,
  LockKeyhole,
  Mail,
  MessageSquare,
  Mic,
  Plus,
  ShieldCheck,
  Square,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import type { AgentResponse, Health, Message } from "./types";
import { useVoice } from "./useVoice";

const timeLabel = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const activityNames: Record<string, string> = {
  clarification_requested: "Asked for a missing detail",
  draft_created: "Draft ready for review",
  navigation_started: "Opening visible browser",
  navigation_completed_no_dom_read: "Page opened · no text read",
  permission_requested: "Waiting for your permission",
  permission_granted: "You allowed one page read",
  permission_denied: "You denied page access",
  permission_expired: "Permission expired · access blocked",
  dom_read_completed: "Approved page text read",
  read_blocked_page_changed: "Page changed · access blocked",
  task_cancelled: "Task cancelled",
};

function Mark({ small = false }: { small?: boolean }) {
  return (
    <div className={`mark ${small ? "small" : ""}`} aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [current, setCurrent] = useState<AgentResponse | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [mode, setMode] = useState<"whisper" | "browser">("whisper");
  const [view, setView] = useState<"assistant" | "drafts" | "privacy">(
    "assistant",
  );
  const [copied, setCopied] = useState(false);
  const [seconds, setSeconds] = useState(60);
  const sending = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const voiceRef = useRef({ recording: false, transcribing: false });
  const permission = current?.status === "PERMISSION_REQUIRED" ? current : null;
  const drafts = messages.filter(
    (message) => message.response?.data.draft_content,
  );
  const audit = current?.data.audit || [];

  useEffect(() => {
    const controller = new AbortController();
    const check = async () => {
      try {
        const response = await fetch("/health", { signal: controller.signal });
        if (!response.ok) throw new Error();
        setHealth(await response.json());
      } catch {
        if (!controller.signal.aborted) setHealth(null);
      }
    };
    void check();
    const interval = setInterval(check, 15000);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);
  useEffect(() => {
    if (permission && !dialog.current?.open) dialog.current?.showModal();
    if (!permission && dialog.current?.open) dialog.current.close();
  }, [permission]);
  useEffect(() => {
    if (!permission?.data.expires_at) return;
    const update = () =>
      setSeconds(
        Math.max(0, Math.ceil(permission.data.expires_at! - Date.now() / 1000)),
      );
    update();
    const timer = setInterval(update, 500);
    return () => clearInterval(timer);
  }, [permission]);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const speak = useCallback(
    (text: string) => {
      if (muted || !window.speechSynthesis) return;
      const voice = window.speechSynthesis
        .getVoices()
        .find((v) => v.localService && v.lang.startsWith("en"));
      if (!voice) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(
        text.replace(/[*#]/g, "").slice(0, 1300),
      );
      utterance.voice = voice;
      utterance.rate = 1.03;
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = utterance.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(utterance);
    },
    [muted],
  );
  useEffect(() => {
    window.speechSynthesis?.getVoices();
  }, []);

  const send = useCallback(
    async (text: string, decision?: boolean, silent = false) => {
      if (sending.current || (!text.trim() && decision === undefined)) return;
      sending.current = true;
      setBusy(true);
      setError("");
      setSpeaking(false);
      window.speechSynthesis?.cancel();
      if (!silent)
        setMessages((old) => [
          ...old,
          { id: crypto.randomUUID(), role: "user", text, time: timeLabel() },
        ]);
      setInput("");
      setView("assistant");
      if (!silent) speak("Let me work on that.");
      try {
        const response = await fetch("/agent/turn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: AbortSignal.timeout(90000),
          body: JSON.stringify({
            session_id: sessionId,
            text,
            pending_interrupt_id: current?.interrupt_id || null,
            user_permission_granted: decision ?? null,
          }),
        });
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "The request could not be processed. Please try again.",
          );
        const result = data as AgentResponse;
        setCurrent(result);
        setMessages((old) => [
          ...old,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: result.speech_to_say,
            response: result,
            time: timeLabel(),
          },
        ]);
        speak(result.speech_to_say);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Connection failed. Check that the backend is running.",
        );
      } finally {
        sending.current = false;
        setBusy(false);
      }
    },
    [sessionId, current, speak],
  );
  const voice = useVoice((text) => void send(text), setError);
  voiceRef.current = voice;
  useEffect(() => {
    if (
      permission &&
      seconds === 0 &&
      !busy &&
      !voiceRef.current.recording &&
      !voiceRef.current.transcribing
    )
      void send("Permission expired", false, true);
  }, [seconds, permission, busy, send]);
  const newTask = async () => {
    if (busy || voice.recording || voice.transcribing) return;
    if (current) await send("cancel", undefined, true);
    setSessionId(crypto.randomUUID());
    setCurrent(null);
    setInput("");
    setView("assistant");
    setError("");
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    inputRef.current?.focus();
  };
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Clipboard unavailable. Select and copy the draft text.");
    }
  };
  const download = (text: string) => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "forma-draft.txt";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const disabled = busy || voice.transcribing;
  const mic = (
    <button
      className={`mic-button ${voice.recording ? "recording" : ""}`}
      aria-label={voice.recording ? "Stop recording" : "Start voice input"}
      disabled={disabled || (mode === "whisper" && !health?.speech.available)}
      onClick={() => void voice.toggle(mode)}
    >
      {voice.recording ? <Square size={18} /> : <Mic size={19} />}
    </button>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(event) => {
            event.preventDefault();
            setView("assistant");
          }}
        >
          <Mark />
          <span>
            forma<span className="brand-dot">.</span>
          </span>
        </a>
        <button
          className="new-task"
          onClick={() => void newTask()}
          disabled={disabled || voice.recording}
        >
          <Plus size={17} /> New task <span>↗</span>
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button
            className={view === "assistant" ? "selected" : ""}
            onClick={() => setView("assistant")}
          >
            <MessageSquare size={18} /> Assistant <span className="nav-dot" />
          </button>
          <button
            className={view === "drafts" ? "selected" : ""}
            onClick={() => setView("drafts")}
          >
            <FileText size={18} /> My drafts{" "}
            <span className="count">{drafts.length}</span>
          </button>
          <button
            className={view === "privacy" ? "selected" : ""}
            onClick={() => setView("privacy")}
          >
            <ShieldCheck size={18} /> Privacy & permissions
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <div className="local-card-icon">
              <Laptop size={19} />
              <span className={health ? "dot" : "dot offline"} />
            </div>
            <strong>Your machine. Your control.</strong>
            <p>Local intelligence, with permission at every page read.</p>
            <span className="tiny-label">NO CLOUD API KEYS</span>
          </div>
          <div className="profile">
            <div className="avatar">Y</div>
            <div>
              <strong>Your workspace</strong>
              <span>Local session</span>
            </div>
            <LockKeyhole size={14} />
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {view === "assistant"
                ? "Assistant"
                : view === "drafts"
                  ? "My drafts"
                  : "Privacy & permissions"}
            </strong>
          </div>
          <span className="connection">
            <span className={health ? "dot" : "dot offline"} />
            {health ? "Running locally" : "Connecting to backend"}
          </span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div className="eyebrow">
              <span /> YOUR EVERYDAY, A LITTLE EASIER
            </div>
            <h1>
              {view === "assistant"
                ? "Less clicking. More doing."
                : view === "drafts"
                  ? "A good place to start."
                  : "You’re always in control."}
            </h1>
            <p>
              {view === "assistant"
                ? "Just say what you need. Forma will take it from here—with your permission."
                : view === "drafts"
                  ? "Your drafts stay here for you to review, copy, or download."
                  : "See exactly what stays local and when your agent can read a page."}
            </p>
          </div>
          {view === "assistant" ? (
            <div className="workspace-grid">
              <section
                className="conversation-card"
                aria-label="Assistant conversation"
              >
                <div className="card-top">
                  <div>
                    <span className="assistant-icon">
                      <AudioLines size={18} />
                    </span>
                    <strong>Assistant</strong>
                    <span className="local-pill">LOCAL</span>
                  </div>
                  <button
                    className="icon-button"
                    aria-label={
                      muted ? "Enable voice responses" : "Mute voice responses"
                    }
                    onClick={() => {
                      setMuted(!muted);
                      window.speechSynthesis?.cancel();
                      setSpeaking(false);
                    }}
                  >
                    {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
                  </button>
                </div>
                <div
                  className={`messages ${messages.length ? "has-messages" : ""}`}
                  aria-live="polite"
                  aria-relevant="additions text"
                >
                  {messages.length === 0 ? (
                    <div className="welcome">
                      <div className="orb">
                        <div className="orb-inner">
                          <AudioLines size={39} strokeWidth={1.4} />
                        </div>
                      </div>
                      <span className="ready-label">
                        <span className="dot" /> READY WHEN YOU ARE
                      </span>
                      <h2>What can I help you with?</h2>
                      <p>
                        Draft that email. Explore a website.
                        <br />
                        Start with a thought, and we’ll work out the details.
                      </p>
                      <div className="suggestions">
                        <button
                          disabled={disabled}
                          onClick={() => void send("Draft an email to Sarah")}
                        >
                          <Mail size={17} />
                          <span>
                            Draft an email<small>Find the right words</small>
                          </span>
                          <ArrowUpRight size={16} />
                        </button>
                        <button
                          disabled={disabled}
                          onClick={() =>
                            void send("Open the demo page and summarize it")
                          }
                        >
                          <Globe2 size={17} />
                          <span>
                            Explore a website
                            <small>Read with your permission</small>
                          </span>
                          <ArrowUpRight size={16} />
                        </button>
                      </div>
                      <button
                        className="subtle-link"
                        disabled={disabled}
                        onClick={() => void send("Prepare a meeting with Alex")}
                      >
                        Or, help me plan a meeting <ChevronRight size={13} />
                      </button>
                    </div>
                  ) : (
                    messages.map((message) => (
                      <div
                        className={`message ${message.role}`}
                        key={message.id}
                      >
                        {message.role === "assistant" ? (
                          <Mark small />
                        ) : (
                          <div className="message-avatar">Y</div>
                        )}
                        <div className="message-content">
                          <div className="message-meta">
                            <strong>
                              {message.role === "assistant" ? "Forma" : "You"}
                            </strong>
                            <time>{message.time}</time>
                          </div>
                          <div
                            className={`bubble ${message.response?.status === "ERROR" ? "error-bubble" : ""}`}
                          >
                            {message.text}
                          </div>
                          {message.response?.data.draft_content && (
                            <div className="draft-output">
                              <div>
                                <FileText size={16} />
                                <strong>Draft · ready for review</strong>
                                <span>
                                  {message.response.data.engine === "ollama"
                                    ? "Local model"
                                    : "Template"}
                                </span>
                              </div>
                              <pre>{message.response.data.draft_content}</pre>
                              <div className="draft-actions">
                                <button
                                  onClick={() =>
                                    void copy(
                                      message.response!.data.draft_content!,
                                    )
                                  }
                                >
                                  {copied ? (
                                    <Check size={14} />
                                  ) : (
                                    <Copy size={14} />
                                  )}{" "}
                                  Copy
                                </button>
                                <button
                                  onClick={() =>
                                    download(
                                      message.response!.data.draft_content!,
                                    )
                                  }
                                >
                                  <Download size={14} /> Download
                                </button>
                              </div>
                            </div>
                          )}
                          {message.response?.action_type ===
                            "BROWSER_SUMMARIZED" && (
                            <div className="source-label">
                              <Globe2 size={13} />
                              <a
                                href={message.response.data.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {message.response.data.url}
                              </a>
                              <span>
                                {message.response.data.engine === "excerpt"
                                  ? "Page excerpt"
                                  : "Local summary"}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                  {busy && (
                    <div className="thinking">
                      <Mark small />
                      <span>
                        <i />
                        <i />
                        <i />
                      </span>
                      <p>
                        {permission
                          ? "Processing your decision"
                          : "Working on your request"}
                      </p>
                    </div>
                  )}
                  <div ref={bottom} />
                </div>
                <div className="composer-area">
                  {error && (
                    <div className="error-notice" role="alert">
                      {error}
                      <button
                        aria-label="Dismiss error"
                        onClick={() => setError("")}
                      >
                        <X size={15} />
                      </button>
                    </div>
                  )}
                  {(voice.recording || voice.transcribing || speaking) && (
                    <div className="voice-status">
                      <AudioLines size={14} />
                      {voice.recording
                        ? "Listening locally… Click stop when you’re done."
                        : voice.transcribing
                          ? "Transcribing on your machine…"
                          : "Forma is speaking…"}
                    </div>
                  )}
                  <form
                    className="composer"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!voice.recording) void send(input);
                    }}
                  >
                    <textarea
                      ref={inputRef}
                      aria-label="Message Forma"
                      rows={1}
                      value={input}
                      disabled={disabled || voice.recording}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          if (!voice.recording) void send(input);
                        }
                      }}
                      placeholder={
                        current?.status === "CLARIFICATION_NEEDED"
                          ? "Add the missing detail…"
                          : "Ask anything, or use your voice…"
                      }
                    />
                    <div className="composer-controls">
                      {mic}
                      <span />
                      <button
                        className="send-button"
                        aria-label="Send message"
                        disabled={disabled || voice.recording || !input.trim()}
                        type="submit"
                      >
                        <ArrowUp size={19} />
                      </button>
                    </div>
                  </form>
                  <div className="composer-caption">
                    <span>
                      <LockKeyhole size={11} /> Voice & AI stay on this device
                    </span>
                    <span>
                      Enter to send <span className="keycap">↵</span>
                    </span>
                  </div>
                </div>
              </section>
              <aside className="context-panel">
                <section className="context-section">
                  <div className="section-label">
                    YOU’RE IN CONTROL <ShieldCheck size={16} />
                  </div>
                  <h3>
                    A helpful agent.
                    <br />A thoughtful boundary.
                  </h3>
                  <p>
                    Forma can open a website, but it asks before reading what’s
                    on it.
                  </p>
                  <div
                    className={`permission-state ${permission ? "pending" : ""}`}
                  >
                    <div className="shield-circle">
                      <LockKeyhole size={18} />
                    </div>
                    <div>
                      <strong>
                        {permission
                          ? "Permission requested"
                          : current?.data.dom_read
                            ? "One page read approved"
                            : "Page access is locked"}
                      </strong>
                      <span>
                        {permission
                          ? "Waiting for your decision"
                          : current?.data.dom_read
                            ? "Future reads need new permission"
                            : "Nothing is read without asking"}
                      </span>
                    </div>
                  </div>
                </section>
                <section className="context-section session-section">
                  <div className="section-label">
                    THIS SESSION <span className="live-dot" />
                  </div>
                  <div className="status-row">
                    <span>Intelligence</span>
                    <strong>
                      {health?.llm.available
                        ? health.llm.model
                        : "Template fallback"}
                    </strong>
                  </div>
                  <div className="status-row">
                    <span>Speech input</span>
                    <strong>
                      {health?.speech.available
                        ? "Whisper · local"
                        : "Text ready"}
                    </strong>
                  </div>
                  <div className="status-row">
                    <span>Browser</span>
                    <strong>
                      {health?.browser.headless
                        ? "Headless test mode"
                        : "Visible Chromium"}
                    </strong>
                  </div>
                  <label className="speech-select">
                    Voice engine
                    <select
                      value={mode}
                      onChange={(event) =>
                        setMode(event.target.value as "whisper" | "browser")
                      }
                      disabled={voice.recording || disabled}
                    >
                      <option value="whisper">Local Whisper</option>
                      <option value="browser">Browser · on-device only</option>
                    </select>
                  </label>
                </section>
                <section className="context-section activity-section">
                  <div className="section-label">
                    ACTIVITY{" "}
                    <span className="activity-count">{audit.length}</span>
                  </div>
                  {audit.length ? (
                    <ol className="activity-list">
                      {audit.slice(-6).map((item, index) => (
                        <li key={`${item.at}-${index}`}>
                          <Check size={12} />
                          <div>
                            {activityNames[item.event] || item.event}
                            <time>
                              {new Date(item.at * 1000).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </time>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <div className="empty-activity">
                      <div>
                        <CheckCheck size={21} />
                      </div>
                      <p>
                        A fresh start.
                        <br />
                        <span>Your task steps will appear here.</span>
                      </p>
                    </div>
                  )}
                </section>
                <div className="tip">
                  <Headphones size={17} />
                  <p>
                    A quiet space helps.
                    <br />
                    <span>You can always type instead.</span>
                  </p>
                </div>
              </aside>
            </div>
          ) : view === "drafts" ? (
            <section className="drafts-view">
              {drafts.length ? (
                drafts.map((message) => (
                  <article className="saved-draft" key={message.id}>
                    <div>
                      <FileText size={19} />
                      <strong>
                        {String(message.response?.data.kind || "Email")} draft
                      </strong>
                      <time>{message.time}</time>
                    </div>
                    <pre>{message.response!.data.draft_content}</pre>
                    <div className="draft-actions">
                      <button
                        onClick={() =>
                          void copy(message.response!.data.draft_content!)
                        }
                      >
                        <Copy size={15} /> {copied ? "Copied" : "Copy draft"}
                      </button>
                      <button
                        onClick={() =>
                          download(message.response!.data.draft_content!)
                        }
                      >
                        <Download size={15} /> Download
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <div className="empty-view">
                  <FileText size={35} />
                  <h2>Your next draft starts with a thought.</h2>
                  <p>Tell Forma who it’s for. It will ask for the details.</p>
                  <button
                    className="primary"
                    onClick={() => {
                      setView("assistant");
                      void send("Draft an email");
                    }}
                  >
                    Create a draft <ArrowUpRight size={16} />
                  </button>
                </div>
              )}
            </section>
          ) : (
            <section className="privacy-view">
              <article>
                <ShieldCheck />
                <h2>Permission belongs to you.</h2>
                <p>
                  Each page read needs a fresh Allow decision. Approval expires
                  after 60 seconds and is invalidated when the page navigates.
                  Saying “deny” or “cancel” stops the task.
                </p>
              </article>
              <article>
                <Laptop />
                <h2>Local by design.</h2>
                <p>
                  Ollama handles generation on your machine. Whisper transcribes
                  locally. Optional browser recognition runs only if on-device
                  processing is supported. Speech output uses a local system
                  voice.
                </p>
              </article>
              <article>
                <Globe2 />
                <h2>Browsing still uses the internet.</h2>
                <p>
                  Opening a public website contacts that website. The agent uses
                  a separate browser profile and reads at most 12,000 characters
                  of visible page text after approval.
                </p>
              </article>
              <article>
                <FileText />
                <h2>Drafts remain drafts.</h2>
                <p>
                  Emails and meeting proposals are prepared for review. Nothing
                  is sent or scheduled. Conversation state is kept in memory;
                  reloading clears this view.
                </p>
              </article>
            </section>
          )}
          <footer>
            <span>
              <Mark small /> Made for your flow. Built around your trust.
            </span>
            <button onClick={() => setView("privacy")}>
              <CircleHelp size={14} /> How Forma works{" "}
              <ArrowUpRight size={12} />
            </button>
          </footer>
        </div>
      </main>
      <dialog
        ref={dialog}
        onCancel={(event) => {
          event.preventDefault();
          if (!disabled && !voice.recording) void send("Deny", false);
        }}
        className="permission-dialog"
        aria-labelledby="permission-title"
        aria-describedby="permission-description"
      >
        <div className="dialog-icon">
          <ShieldCheck size={28} />
        </div>
        <span className="eyebrow">A QUICK PERMISSION CHECK</span>
        <h2 id="permission-title">May I read this page?</h2>
        <p id="permission-description">
          The browser is open. Allow Forma to read this page’s visible text once
          and create a local summary.
        </p>
        <div className="permission-url">
          <Globe2 size={17} />
          <span>{permission?.data.url}</span>
        </div>
        <div className="permission-details">
          <span>
            <Check size={14} /> Up to 12,000 characters
          </span>
          <span>
            <Check size={14} /> One page, one read
          </span>
          <span>
            <LockKeyhole size={14} /> No page text read yet
          </span>
        </div>
        <div className="dialog-actions">
          <button
            disabled={disabled || voice.recording}
            onClick={() => void send("Deny", false)}
          >
            Deny access
          </button>
          <button
            className="primary"
            autoFocus
            disabled={disabled || voice.recording || seconds === 0}
            onClick={() => void send("Allow", true)}
          >
            Allow once <ArrowUpRight size={16} />
          </button>
        </div>
        <div className="dialog-voice">
          {mic}
          <span>
            {voice.recording
              ? "Listening… Say “allow” or “deny”, then stop."
              : voice.transcribing
                ? "Transcribing locally…"
                : `Or say “allow” or “deny” · expires in ${seconds}s`}
          </span>
        </div>
        {error && (
          <p role="alert" className="dialog-error">
            {error}
          </p>
        )}
      </dialog>
    </div>
  );
}

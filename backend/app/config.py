import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    llm_enabled: bool = os.getenv("AGENT_LLM_ENABLED", "true").lower() == "true"
    headless: bool = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
    permission_ttl: int = int(os.getenv("PERMISSION_TTL_SECONDS", "60"))
    session_ttl: int = 3600
    max_sessions: int = 40
    max_page_chars: int = 12000
    whisper_model: str = os.getenv(
        "WHISPER_MODEL", str(ROOT / ".runtime/models/ggml-base.en.bin")
    )
    whisper_bin: str = os.getenv("WHISPER_BIN", "whisper-cli")

    def __post_init__(self):
        target = urlsplit(self.ollama_url)
        if (
            target.scheme not in {"http", "https"}
            or target.hostname not in {"localhost", "127.0.0.1", "::1"}
            or target.username
            or target.password
        ):
            raise ValueError("OLLAMA_URL must point to a local loopback server.")
        if self.model.endswith("cloud"):
            raise ValueError("Use a downloaded local model; cloud models are disabled.")


settings = Settings()

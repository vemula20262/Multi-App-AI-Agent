import asyncio
import io
import re
import shutil
import tempfile
import wave
from pathlib import Path

from fastapi import HTTPException


class LocalSpeech:
    def __init__(self, settings):
        self.settings = settings
        self.lock = asyncio.Lock()

    def health(self):
        available = bool(
            shutil.which(self.settings.whisper_bin)
            and Path(self.settings.whisper_model).is_file()
        )
        return {"available": available, "engine": "whisper.cpp", "local": True}

    async def transcribe(self, audio):
        if not self.health()["available"]:
            raise HTTPException(
                503,
                "Local speech is not set up. Run scripts/setup-local-models.sh, or use text input.",
            )
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                if (
                    wav.getnchannels() != 1
                    or wav.getsampwidth() != 2
                    or wav.getframerate() != 16000
                ):
                    raise ValueError()
                if not 0 < wav.getnframes() <= 16000 * 60:
                    raise ValueError()
        except (wave.Error, ValueError, EOFError):
            raise HTTPException(
                400, "Send up to 60 seconds of 16 kHz mono PCM16 WAV audio."
            )
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix="local-agent-audio-") as temp:
                path = Path(temp) / "speech.wav"
                path.write_bytes(audio)
                process = await asyncio.create_subprocess_exec(
                    self.settings.whisper_bin,
                    "-m",
                    self.settings.whisper_model,
                    "-f",
                    str(path),
                    "-l",
                    "en",
                    "-nt",
                    "-np",
                    "-otxt",
                    "-of",
                    str(Path(temp) / "transcript"),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    await asyncio.wait_for(process.communicate(), timeout=60)
                except (TimeoutError, asyncio.CancelledError):
                    process.kill()
                    await process.wait()
                    raise HTTPException(
                        504, "Local transcription timed out. Try a shorter recording."
                    )
                output = Path(temp) / "transcript.txt"
                if process.returncode or not output.exists():
                    raise HTTPException(
                        500,
                        "Local transcription failed. Try again or type your message.",
                    )
                text = re.sub(
                    r"\[[^\]]+\]|\([^)]*(?:music|silence)[^)]*\)",
                    "",
                    output.read_text(),
                    flags=re.IGNORECASE,
                ).strip()
                return {"text": text, "engine": "whisper.cpp", "local": True}

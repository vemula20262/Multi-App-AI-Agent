import io
import wave
from dataclasses import replace

import httpx
import pytest
from app.browser import DEMO_URL, BrowserBoundaryError, validate_url
from app.config import settings
from app.main import app
from app.speech import LocalSpeech


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def test_shared_contract(client):
    response = await client.post(
        "/agent/turn",
        json={
            "session_id": "api-email",
            "text": "Draft an email to Sarah",
            "pending_interrupt_id": None,
            "user_permission_granted": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CLARIFICATION_NEEDED"
    assert set(response.json()) == {
        "status",
        "interrupt_id",
        "speech_to_say",
        "action_type",
        "data",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "", "text": "hi"},
        {"session_id": "x", "text": ""},
        {"session_id": "x", "text": "hi", "user_permission_granted": "true"},
        {"session_id": "../x", "text": "hi"},
    ],
)
async def test_invalid_requests(client, payload):
    response = await client.post("/agent/turn", json=payload)
    assert response.status_code == 422


async def test_untrusted_origin_blocked(client):
    response = await client.post(
        "/agent/turn",
        headers={"Origin": "https://evil.example"},
        json={"session_id": "x", "text": "Allow"},
    )
    assert response.status_code == 403


async def test_dns_rebinding_host_blocked(client):
    response = await client.get("/health", headers={"Host": "attacker.example:8000"})
    assert response.status_code == 403


async def test_demo_is_available(client):
    response = await client.get("/demo")
    assert response.status_code == 200
    assert "community garden" in response.text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://127.0.0.1:22",
        "http://localhost:8000/health",
        "https://user:password@example.com",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
async def test_nonpublic_urls_blocked(url):
    with pytest.raises(BrowserBoundaryError):
        await validate_url(url)


async def test_builtin_demo_allowed():
    assert await validate_url(DEMO_URL) == DEMO_URL


async def test_unavailable_speech_reports_actionable_error():
    from fastapi import HTTPException

    speech = LocalSpeech(replace(settings, whisper_model="/nonexistent/model.bin"))
    with pytest.raises(HTTPException) as error:
        await speech.transcribe(b"invalid")
    assert error.value.status_code == 503


async def test_speech_rejects_wrong_wav(monkeypatch):
    from fastapi import HTTPException

    speech = LocalSpeech(settings)
    monkeypatch.setattr(speech, "health", lambda: {"available": True})
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\x00" * 400)
    with pytest.raises(HTTPException) as error:
        await speech.transcribe(audio.getvalue())
    assert error.value.status_code == 400


def test_model_configuration_is_local_only():
    with pytest.raises(ValueError, match="loopback"):
        replace(settings, ollama_url="https://remote.example")
    with pytest.raises(ValueError, match="cloud"):
        replace(settings, model="gpt-oss:120b-cloud")

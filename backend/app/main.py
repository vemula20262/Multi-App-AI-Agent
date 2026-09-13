import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .agent import Agent
from .browser import BrowserDriver
from .config import settings
from .llm import LocalModel
from .schemas import TurnRequest, TurnResponse
from .speech import LocalSpeech

browser = BrowserDriver(settings)
model = LocalModel(settings)
agent = Agent(settings, browser, model)
speech = LocalSpeech(settings)


@asynccontextmanager
async def lifespan(app):
    async def cleanup():
        while True:
            await asyncio.sleep(5)
            await agent.reap()

    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await browser.close()
    await model.client.aclose()


app = FastAPI(title="Local Voice Agent", version="0.1.0", lifespan=lifespan)
ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    # Prevent arbitrary websites from driving the local browser via cross-origin POSTs.
    from fastapi.responses import JSONResponse

    if (
        request.headers.get("origin")
        and request.headers["origin"] not in ALLOWED_ORIGINS
    ):
        return JSONResponse({"detail": "Origin not permitted."}, status_code=403)
    host = request.headers.get("host", "").split(":")[0]
    if host not in {"localhost", "127.0.0.1", "testserver"}:
        return JSONResponse({"detail": "Local connections only."}, status_code=403)
    return await call_next(request)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm": await model.health(),
        "speech": speech.health(),
        "browser": {
            "headless": settings.headless,
            "installed": Path(browser.playwright.chromium.executable_path).exists()
            if browser.playwright
            else None,
        },
        "permission_ttl_seconds": settings.permission_ttl,
    }


@app.post("/agent/turn", response_model=TurnResponse)
async def turn(request: TurnRequest):
    return await agent.turn(request)


@app.post("/speech/transcribe")
async def transcribe(request: Request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2_000_000:
            raise HTTPException(
                413, "Recording too large. Keep recordings under 60 seconds."
            )
        chunks.append(chunk)
    return await speech.transcribe(b"".join(chunks))


@app.get("/demo", response_class=HTMLResponse)
async def demo():
    return """<!doctype html><html><head><title>Local Dispatch — Demo</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>
    body{font:18px/1.7 system-ui;background:#f4f2e9;color:#23382d;max-width:800px;margin:80px auto;padding:24px}small{letter-spacing:3px}h1{font:64px Georgia}article{border-top:1px solid #bdc9bc;padding:20px 0}h2{font:28px Georgia}aside{padding:18px;background:#e1e9dc;border-radius:12px}
    </style></head><body><small>LOCAL DISPATCH / DEMO EDITION</small><h1>A little more local.</h1>
    <aside>This is a fictional demo page. Your agent must request permission before reading its text.</aside>
    <article><h2>A new community garden takes root</h2><p>Riverside volunteers opened a community garden on Saturday. Twenty raised beds will grow vegetables for the neighborhood food pantry.</p></article>
    <article><h2>The library is staying open later</h2><p>The central library will stay open until 9 p.m. on Tuesdays and Thursdays beginning next month, giving students more evening study time.</p></article>
    <article><h2>Repair, reuse, repeat</h2><p>A free repair café meets on the first Sunday of each month. Volunteers help residents fix small appliances and mend clothing.</p></article>
    </body></html>"""

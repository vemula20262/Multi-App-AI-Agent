import asyncio
import ipaddress
import socket
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from .config import Settings

DEMO_URL = "http://127.0.0.1:8000/demo"


class BrowserBoundaryError(Exception):
    pass


async def validate_url(url: str):
    parsed = urlsplit(url)
    if url == DEMO_URL:
        return url
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise BrowserBoundaryError("Use a public http or https website URL.")
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except (OSError, ValueError):
        raise BrowserBoundaryError("That website address could not be resolved.")
    if any(not ipaddress.ip_address(row[4][0]).is_global for row in records):
        raise BrowserBoundaryError(
            "Private network addresses are blocked. Use a public website or the built-in demo."
        )
    return url


@dataclass
class BrowserTab:
    page: object
    context: object
    revision: int = 0
    reads: int = 0


class BrowserDriver:
    """Only read() may inspect page content. Navigation never reads DOM/title/screenshots."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.tabs: dict[str, BrowserTab] = {}
        self.playwright = None
        self.browser = None
        self.launch_lock = asyncio.Lock()

    async def _launch(self):
        async with self.launch_lock:
            if self.browser and self.browser.is_connected():
                return
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.headless,
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )

    async def navigate(self, session_id, url):
        await validate_url(url)
        await self._launch()
        await self.close_session(session_id)
        context = await self.browser.new_context(accept_downloads=False)

        # Validate all network requests without inspecting response bodies or DOM.
        async def network_guard(route):
            try:
                await validate_url(route.request.url)
                await route.continue_()
            except (BrowserBoundaryError, ValueError):
                await route.abort("blockedbyclient")

        await context.route("**/*", network_guard)
        page = await context.new_page()
        tab = BrowserTab(page, context)
        self.tabs[session_id] = tab

        def navigated(frame):
            if frame == page.main_frame:
                tab.revision += 1

        page.on("framenavigated", navigated)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.bring_to_front()
            await validate_url(page.url)
            return {"url": page.url, "revision": tab.revision}
        except Exception:
            await self.close_session(session_id)
            raise

    def location(self, session_id):
        tab = self.tabs.get(session_id)
        if not tab or tab.page.is_closed():
            raise BrowserBoundaryError(
                "The browser tab was closed. Open the website again."
            )
        return {"url": tab.page.url, "revision": tab.revision}

    async def read(self, session_id, expected_url, expected_revision):
        tab = self.tabs.get(session_id)
        if self.location(session_id) != {
            "url": expected_url,
            "revision": expected_revision,
        }:
            raise BrowserBoundaryError(
                "The page changed. Open it again to request fresh permission."
            )
        # This is the sole DOM access boundary. The caller consumes one valid consent first.
        # Re-check location inside the same JS task as extraction to prevent navigation races.
        result = await tab.page.evaluate(
            """({url, limit}) => {
          if (location.href !== url) return null;
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          let out = '', node;
          while ((node = walker.nextNode()) && out.length < limit) {
            const el = node.parentElement;
            if (!el || el.closest('script, style, noscript, input, textarea, select, [contenteditable="true"], [hidden], [aria-hidden="true"]')) continue;
            if (!el.getClientRects().length || getComputedStyle(el).visibility === 'hidden') continue;
            const text = node.textContent.trim();
            if (text) out += text + '\\n';
          }
          return out.slice(0, limit);
        }""",
            {"url": expected_url, "limit": self.settings.max_page_chars},
        )
        if result is None or tab.revision != expected_revision:
            raise BrowserBoundaryError(
                "The page changed during inspection. Request fresh permission."
            )
        tab.reads += 1
        return result

    async def close_session(self, session_id):
        tab = self.tabs.pop(session_id, None)
        if tab:
            with suppress(PlaywrightError, RuntimeError):
                await tab.context.close()

    async def close(self):
        for sid in list(self.tabs):
            await self.close_session(sid)
        if self.browser:
            with suppress(PlaywrightError, RuntimeError):
                await self.browser.close()
        if self.playwright:
            with suppress(PlaywrightError, RuntimeError):
                await self.playwright.stop()
        self.browser = self.playwright = None

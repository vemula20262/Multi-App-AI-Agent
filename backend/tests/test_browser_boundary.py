"""Verify the browser adapter itself, including its no-inspection navigation path."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.browser import DEMO_URL, BrowserBoundaryError, BrowserDriver, BrowserTab
from app.config import settings


async def test_navigation_does_not_inspect_content():
    driver = BrowserDriver(settings)
    page = MagicMock()
    page.url = DEMO_URL
    page.goto = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.evaluate = AsyncMock()
    page.inner_text = AsyncMock()
    page.title = AsyncMock()
    page.content = AsyncMock()
    page.screenshot = AsyncMock()
    context = MagicMock()
    context.route = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    driver.browser = MagicMock()
    driver.browser.new_context = AsyncMock(return_value=context)
    driver._launch = AsyncMock()
    result = await driver.navigate("test", DEMO_URL)
    assert result["url"] == DEMO_URL
    page.goto.assert_awaited_once()
    for method in [
        page.evaluate,
        page.inner_text,
        page.title,
        page.content,
        page.screenshot,
    ]:
        method.assert_not_awaited()


async def test_read_checks_revision_before_any_dom_operation():
    driver = BrowserDriver(settings)
    page = MagicMock()
    page.url = DEMO_URL
    page.is_closed.return_value = False
    page.evaluate = AsyncMock(return_value="text")
    driver.tabs["test"] = BrowserTab(page, MagicMock(), revision=2)
    with pytest.raises(BrowserBoundaryError):
        await driver.read("test", DEMO_URL, 1)
    page.evaluate.assert_not_awaited()

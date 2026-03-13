from playwright.async_api import async_playwright, Playwright, Browser

_playwright: Playwright | None = None
_browser: Browser | None = None

LAUNCH_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]


async def launch_browser() -> Browser:
    global _playwright, _browser
    if _browser:
        return _browser

    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=LAUNCH_ARGS,
    )
    _browser.on("disconnected", lambda: _on_disconnected())
    return _browser


def _on_disconnected():
    global _browser
    _browser = None


def get_browser() -> Browser:
    if _browser is None:
        raise RuntimeError("Browser not launched — call launch_browser() first")
    return _browser


def get_playwright() -> Playwright:
    if _playwright is None:
        raise RuntimeError("Playwright not started — call launch_browser() first")
    return _playwright


async def close_browser():
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None

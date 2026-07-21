import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .manager import get_browser, get_playwright, LAUNCH_ARGS
from ..db import insert_context, update_context_status, insert_log

ROOT = Path(__file__).parent.parent.parent
PROFILES_DIR = ROOT / "profiles"
SCREENSHOTS_DIR = ROOT / "data" / "screenshots"

# In-memory map: id -> { context, page, meta }
_alive: dict[str, dict] = {}

# Uploaded screenshots for external contexts: id -> png bytes
_screenshots: dict[str, bytes] = {}

# Throttle disk saves: id -> last save timestamp
_last_save: dict[str, float] = {}
_SAVE_INTERVAL = float(os.environ.get("CLAWSOME_SCREENSHOT_INTERVAL", "1.0"))  # minimum seconds between saves per context

# Dedup disk saves: id -> hash of last saved frame
_last_hash: dict[str, str] = {}


def _save_screenshot(ctx_id: str, png: bytes, *, force: bool = False):
    now = time.time()
    if not force and ctx_id in _last_save and (now - _last_save[ctx_id]) < _SAVE_INTERVAL:
        return
    digest = hashlib.sha256(png).hexdigest()
    if _last_hash.get(ctx_id) == digest:
        return
    _last_save[ctx_id] = now
    _last_hash[ctx_id] = digest
    d = SCREENSHOTS_DIR / ctx_id
    d.mkdir(parents=True, exist_ok=True)
    ts = int(now * 1000)
    (d / f"{ts}.png").write_bytes(png)


def list_screenshots(ctx_id: str) -> list[dict]:
    d = SCREENSHOTS_DIR / ctx_id
    if not d.exists():
        return []
    files = sorted(d.glob("*.png"), reverse=True)
    result = []
    for f in files:
        ts_ms = int(f.stem)
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        result.append({
            "filename": f.name,
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result


def get_saved_screenshot(ctx_id: str, filename: str) -> bytes:
    path = SCREENSHOTS_DIR / ctx_id / filename
    if not path.exists() or not path.name.endswith(".png"):
        raise ValueError(f"Screenshot not found: {filename}")
    return path.read_bytes()

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
"""


async def create_context(*, name: str, profile: str | None = None, external: bool = False) -> dict:
    ctx_id = str(uuid.uuid4())

    if external:
        meta = {
            "id": ctx_id,
            "name": name,
            "profile": None,
            "persistent": False,
            "external": True,
        }
        _alive[ctx_id] = {"context": None, "page": None, "meta": meta}
        insert_context(id=ctx_id, name=name, profile=None)
        return meta

    profile_path = PROFILES_DIR / profile if profile else None
    has_persistent = profile_path is not None and profile_path.exists()

    if has_persistent:
        pw = get_playwright()
        context = await pw.chromium.launch_persistent_context(
            str(profile_path),
            headless=True,
            args=LAUNCH_ARGS,
            viewport={"width": 1280, "height": 720},
        )
        page = context.pages[0] if context.pages else await context.new_page()
    else:
        browser = get_browser()
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

    await page.add_init_script(STEALTH_SCRIPT)

    meta = {
        "id": ctx_id,
        "name": name,
        "profile": profile or None,
        "persistent": has_persistent,
        "external": False,
    }
    _alive[ctx_id] = {"context": context, "page": page, "meta": meta}

    insert_context(id=ctx_id, name=name, profile=profile)

    return meta


def get_alive_context(ctx_id: str) -> dict | None:
    return _alive.get(ctx_id)


def list_alive_contexts() -> list[dict]:
    return [entry["meta"] for entry in _alive.values()]


async def navigate_to(
    ctx_id: str, url: str, *, timeout: int = 30000, wait_until: str = "domcontentloaded"
) -> dict:
    entry = _alive.get(ctx_id)
    if not entry:
        raise ValueError(f"Context {ctx_id} not found")
    await entry["page"].goto(url, wait_until=wait_until, timeout=timeout)
    return {"url": entry["page"].url}


def upload_screenshot(ctx_id: str, png: bytes):
    if ctx_id not in _alive:
        raise ValueError(f"Context {ctx_id} not found")
    _screenshots[ctx_id] = png
    _save_screenshot(ctx_id, png, force=True)


async def take_screenshot(ctx_id: str) -> bytes:
    entry = _alive.get(ctx_id)
    if not entry:
        raise ValueError(f"Context {ctx_id} not found")
    if entry["meta"].get("external"):
        if ctx_id in _screenshots:
            return _screenshots[ctx_id]
        raise ValueError(f"No screenshot available for context {ctx_id}")
    png = await entry["page"].screenshot(type="png")
    _save_screenshot(ctx_id, png)
    return png


async def exec_action(
    ctx_id: str,
    *,
    action: str,
    selector: str | None = None,
    value: str | None = None,
    script: str | None = None,
    timeout: int | None = None,
) -> dict:
    entry = _alive.get(ctx_id)
    if not entry:
        raise ValueError(f"Context {ctx_id} not found")
    page = entry["page"]
    opts = {"timeout": timeout} if timeout else {}

    if action == "click":
        await page.click(selector, **opts)
        return {"action": "click", "selector": selector}

    elif action == "type":
        await page.fill(selector, value, **opts)
        return {"action": "type", "selector": selector, "value": value}

    elif action == "select":
        await page.select_option(selector, value, **opts)
        return {"action": "select", "selector": selector, "value": value}

    elif action == "wait":
        await page.wait_for_selector(selector, **opts)
        return {"action": "wait", "selector": selector}

    elif action == "evaluate":
        result = await page.evaluate(script)
        return {"action": "evaluate", "result": result}

    elif action == "waitForNavigation":
        await page.wait_for_url(selector or "**/*", timeout=timeout or 15000)
        return {"action": "waitForNavigation", "url": page.url}

    elif action == "solveTurnstile":
        log = lambda msg: insert_log(context_id=ctx_id, level="info", message=msg)

        log("Turnstile: checking for challenge iframe...")

        try:
            frame = await page.wait_for_selector(
                'iframe[src*="challenges.cloudflare.com"]',
                timeout=timeout or 10000,
            )
        except Exception:
            frame = None

        if not frame:
            log("Turnstile: no challenge found, proceeding")
            return {"action": "solveTurnstile", "status": "no_challenge", "url": page.url}

        log("Turnstile: challenge detected, clicking checkbox")

        try:
            challenge_frame = await frame.content_frame()
            await challenge_frame.click(
                'input[type="checkbox"], .cb-i', timeout=timeout or 5000
            )
            await page.wait_for_function(
                "() => !document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')",
                timeout=timeout or 15000,
            )
            url = page.url
            log(f"Turnstile: challenge resolved, page URL: {url}")
            return {"action": "solveTurnstile", "status": "solved", "url": url}
        except Exception as err:
            msg = f"Turnstile: challenge handling failed — {err}"
            insert_log(context_id=ctx_id, level="error", message=msg)
            raise ValueError(msg)

    else:
        raise ValueError(f"Unknown action: {action}")


async def destroy_context(ctx_id: str):
    entry = _alive.get(ctx_id)
    if not entry:
        raise ValueError(f"Context {ctx_id} not found")

    if entry["context"]:
        await entry["context"].close()
    del _alive[ctx_id]
    _screenshots.pop(ctx_id, None)
    _last_save.pop(ctx_id, None)
    _last_hash.pop(ctx_id, None)

    update_context_status(ctx_id, "stopped")


async def destroy_all_contexts():
    for ctx_id in list(_alive.keys()):
        try:
            await destroy_context(ctx_id)
        except Exception:
            pass

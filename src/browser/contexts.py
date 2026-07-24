import asyncio
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


def latest_screenshot(ctx_id: str) -> dict | None:
    d = SCREENSHOTS_DIR / ctx_id
    if not d.exists():
        return None
    files = sorted(d.glob("*.png"), reverse=True)
    if not files:
        return None
    f = files[0]
    ts = datetime.fromtimestamp(int(f.stem) / 1000, tz=timezone.utc)
    return {"filename": f.name, "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S")}


def get_saved_screenshot(ctx_id: str, filename: str) -> bytes:
    # Resolve the joined path and confirm it stays within the context's own
    # directory. URL-encoded separators in ctx_id/filename survive route
    # matching, so a crafted value could otherwise traverse out of it.
    root = SCREENSHOTS_DIR.resolve()
    base = (root / ctx_id).resolve()
    path = (base / filename).resolve()
    if (
        base.parent != root
        or path.parent != base
        or not path.name.endswith(".png")
        or not path.is_file()
    ):
        raise ValueError(f"Screenshot not found: {filename}")
    return path.read_bytes()

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
"""

SNAPSHOT_SCRIPT = """
() => {
  function cssEscape(str) {
    return window.CSS && CSS.escape ? CSS.escape(str) : str.replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }

  function selectorFor(el) {
    if (el.id) return '#' + cssEscape(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId) return `[data-testid="${testId}"]`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {
      let part = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(' > ');
  }

  function labelFor(el) {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    if (el.labels && el.labels.length) return Array.from(el.labels).map((l) => l.innerText.trim()).join(' ');
    if (el.tagName === 'SELECT') {
      const selected = el.options[el.selectedIndex];
      return selected ? selected.text.trim() : '';
    }
    const text = el.innerText && el.innerText.trim();
    if (text) return text.slice(0, 120);
    if (el.placeholder) return el.placeholder;
    if (el.value) return String(el.value).slice(0, 120);
    const title = el.getAttribute('title');
    if (title) return title;
    return '';
  }

  function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  }

  const selector = 'a[href], button, input, select, textarea, [role="button"], [role="link"], ' +
    '[role="checkbox"], [role="radio"], [role="tab"], [contenteditable="true"]';

  const elements = Array.from(document.querySelectorAll(selector))
    .filter(visible)
    .slice(0, 200)
    .map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || undefined,
      role: el.getAttribute('role') || undefined,
      label: labelFor(el),
      selector: selectorFor(el),
      href: el.tagName === 'A' ? el.href : undefined,
    }));

  return {
    url: location.href,
    title: document.title,
    text: document.body.innerText.slice(0, 4000),
    elements,
  };
}
"""


DEFAULT_VIEWPORT = {"width": 1280, "height": 720}

# Destroy contexts idle beyond this many seconds. 0 disables expiry.
CONTEXT_TTL = float(os.environ.get("CLAWSOME_CONTEXT_TTL", "1800"))
REAPER_INTERVAL = 30.0


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def touch_context(ctx_id: str):
    """Mark a context as active. Called on any API request that touches it."""
    entry = _alive.get(ctx_id)
    if entry:
        entry["last_activity"] = time.time()
        entry["meta"]["last_activity"] = _now_iso()


class ProfileInUseError(Exception):
    """Raised when a profile is already held by another live context."""

    def __init__(self, profile: str, holder: dict):
        self.profile = profile
        self.holder = holder
        super().__init__(
            f"Profile '{profile}' is in use by context {holder['id']} ('{holder['name']}')"
        )


def _adopt_page(ctx_id: str, page):
    """Make a newly opened page the context's active one (e.g. target="_blank")."""
    entry = _alive.get(ctx_id)
    if not entry:
        return
    entry["page"] = page
    page.on("close", lambda _p=page: _on_page_closed(ctx_id, _p))


def _on_page_closed(ctx_id: str, closed):
    """Fall back to another open page when the active one closes."""
    entry = _alive.get(ctx_id)
    if not entry or entry.get("page") is not closed:
        return
    context = entry.get("context")
    remaining = [p for p in context.pages if not p.is_closed()] if context else []
    entry["page"] = remaining[-1] if remaining else None


def _require_page(ctx_id: str):
    entry = _alive.get(ctx_id)
    if not entry:
        raise ValueError(f"Context {ctx_id} not found")
    page = entry.get("page")
    if page is None:
        raise ValueError(f"Context {ctx_id} has no open page")
    return page


def _profile_holder(profile: str) -> dict | None:
    for entry in _alive.values():
        meta = entry["meta"]
        if meta.get("profile") == profile and meta.get("persistent"):
            return meta
    return None


async def create_context(
    *,
    name: str,
    profile: str | None = None,
    external: bool = False,
    viewport: dict | None = None,
) -> dict:
    ctx_id = str(uuid.uuid4())

    now = time.time()

    if external:
        meta = {
            "id": ctx_id,
            "name": name,
            "profile": None,
            "persistent": False,
            "external": True,
            "viewport": None,
            "created_at": _now_iso(),
            "last_activity": _now_iso(),
        }
        _alive[ctx_id] = {
            "context": None,
            "page": None,
            "meta": meta,
            "last_activity": now,
        }
        insert_context(id=ctx_id, name=name, profile=None)
        return meta

    vp = viewport or DEFAULT_VIEWPORT
    profile_path = PROFILES_DIR / profile if profile else None
    has_persistent = profile_path is not None and profile_path.exists()

    if has_persistent:
        holder = _profile_holder(profile)
        if holder:
            raise ProfileInUseError(profile, holder)
        pw = get_playwright()
        context = await pw.chromium.launch_persistent_context(
            str(profile_path),
            headless=True,
            args=LAUNCH_ARGS,
            viewport=vp,
        )
        page = context.pages[0] if context.pages else await context.new_page()
    else:
        browser = get_browser()
        context = await browser.new_context(viewport=vp)
        page = await context.new_page()

    await page.add_init_script(STEALTH_SCRIPT)

    # Adopt pages opened by the site itself (target="_blank", window.open) so a
    # click that spawns a tab doesn't leave the context pointing at the old page.
    context.on("page", lambda new_page: _adopt_page(ctx_id, new_page))
    page.on("close", lambda _p=page: _on_page_closed(ctx_id, _p))

    meta = {
        "id": ctx_id,
        "name": name,
        "profile": profile or None,
        "persistent": has_persistent,
        "external": False,
        "viewport": vp,
        "created_at": _now_iso(),
        "last_activity": _now_iso(),
    }
    _alive[ctx_id] = {
        "context": context,
        "page": page,
        "meta": meta,
        "last_activity": now,
    }

    insert_context(id=ctx_id, name=name, profile=profile)

    return meta


def get_alive_context(ctx_id: str) -> dict | None:
    return _alive.get(ctx_id)


def list_alive_contexts() -> list[dict]:
    return [entry["meta"] for entry in _alive.values()]


async def page_state(ctx_id: str) -> dict:
    """Current url + title for the context's page, or {} for external contexts."""
    entry = _alive.get(ctx_id)
    if not entry or not entry.get("page"):
        return {}
    page = entry["page"]
    return {"url": page.url, "title": await page.title()}


async def navigate_to(
    ctx_id: str, url: str, *, timeout: int = 30000, wait_until: str = "domcontentloaded"
) -> dict:
    page = _require_page(ctx_id)
    await page.goto(url, wait_until=wait_until, timeout=timeout)
    return {"url": page.url}


async def get_snapshot(ctx_id: str) -> dict:
    return await _require_page(ctx_id).evaluate(SNAPSHOT_SCRIPT)


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
    png = await _require_page(ctx_id).screenshot(type="png")
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
    page = _require_page(ctx_id)
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

    elif action == "scroll":
        if selector:
            await page.locator(selector).scroll_into_view_if_needed(**opts)
        else:
            # value is a pixel delta, or "top"/"bottom"/"page"/"-page"
            amount = (value or "page").strip().lower()
            if amount == "top":
                await page.evaluate("window.scrollTo(0, 0)")
            elif amount == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif amount in ("page", "-page"):
                sign = -1 if amount.startswith("-") else 1
                await page.evaluate(f"window.scrollBy(0, {sign} * window.innerHeight)")
            else:
                try:
                    delta = int(amount)
                except ValueError:
                    raise ValueError(
                        "scroll value must be a pixel amount or one of: top, bottom, page, -page"
                    )
                await page.evaluate(f"window.scrollBy(0, {delta})")
        position = await page.evaluate("({x: window.scrollX, y: window.scrollY})")
        return {"action": "scroll", "selector": selector, "value": value, "position": position}

    elif action == "press":
        if not value:
            raise ValueError("press requires a key in 'value' (e.g. 'Enter')")
        if selector:
            await page.press(selector, value, **opts)
        else:
            await page.keyboard.press(value)
        return {"action": "press", "selector": selector, "value": value}

    elif action == "hover":
        await page.hover(selector, **opts)
        return {"action": "hover", "selector": selector}

    elif action == "back":
        await page.go_back(**opts)
        return {"action": "back"}

    elif action == "reload":
        await page.reload(**opts)
        return {"action": "reload"}

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


async def reap_idle_contexts(on_destroyed=None) -> list[str]:
    """Destroy contexts idle beyond CONTEXT_TTL. Returns the ids reaped."""
    if CONTEXT_TTL <= 0:
        return []
    now = time.time()
    reaped = []
    for ctx_id, entry in list(_alive.items()):
        idle = now - entry.get("last_activity", now)
        if idle < CONTEXT_TTL:
            continue
        insert_log(
            context_id=ctx_id,
            level="warn",
            message=f"Context expired after {int(idle)}s idle (CLAWSOME_CONTEXT_TTL={int(CONTEXT_TTL)}s)",
        )
        try:
            await destroy_context(ctx_id)
        except Exception:
            continue
        reaped.append(ctx_id)
        if on_destroyed:
            on_destroyed(ctx_id)
    return reaped


async def run_reaper(on_destroyed=None):
    """Periodically reap idle contexts. Runs for the lifetime of the app."""
    if CONTEXT_TTL <= 0:
        return
    while True:
        await asyncio.sleep(REAPER_INTERVAL)
        try:
            await reap_idle_contexts(on_destroyed)
        except Exception:
            pass

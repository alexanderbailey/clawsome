"""An MCP server exposing Clawsome's REST API as agent tools.

This is a thin client: it talks HTTP to a running Clawsome instance and does
not drive a browser itself. Start Clawsome first, then point an MCP client at
this server.

    CLAWSOME_URL    address of the Clawsome instance (default http://localhost:3000)
    CLAWSOME_TOKEN  bearer token, if that instance requires one

Run it with:

    uv run --extra mcp python -m src.mcp_server
"""

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP, Image

CLAWSOME_URL = (os.environ.get("CLAWSOME_URL") or "http://localhost:3000").rstrip("/")
CLAWSOME_TOKEN = os.environ.get("CLAWSOME_TOKEN") or None
TIMEOUT = httpx.Timeout(120.0)

mcp = FastMCP(
    "clawsome",
    instructions=(
        "Drive a real browser through a Clawsome instance, with live progress "
        "visible on its dashboard.\n\n"
        "Workflow: create_context -> goto -> snapshot to see what is on the "
        "page -> act -> log progress -> destroy_context when finished.\n\n"
        "Prefer snapshot over guessing selectors: it returns the page's "
        "interactive elements with selectors that work directly in act(). "
        "Always destroy_context when the task is done, even if it failed, so "
        "the browser page is released."
    ),
)


class ClawsomeError(Exception):
    """A failure reported by Clawsome, phrased for the calling agent."""


def _headers(extra: dict | None = None) -> dict[str, Any]:
    headers = dict(extra or {})
    if CLAWSOME_TOKEN:
        headers["Authorization"] = f"Bearer {CLAWSOME_TOKEN}"
    return headers


def _explain(response: httpx.Response) -> str:
    """Turn an error response into something an agent can act on."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:400]}"

    if isinstance(body, dict):
        # Browser failures come back as {error, message, url}; validation and
        # not-found errors as {detail}.
        if "message" in body:
            where = f" (page was at {body['url']})" if body.get("url") else ""
            return f"{body.get('error', 'error')}: {body['message']}{where}"
        if "detail" in body:
            return str(body["detail"])
    return f"HTTP {response.status_code}: {body}"


async def _request(method: str, path: str, *, json=None, headers=None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.request(
                method, f"{CLAWSOME_URL}{path}", json=json, headers=_headers(headers)
            )
        except httpx.RequestError as e:
            raise ClawsomeError(
                f"Could not reach Clawsome at {CLAWSOME_URL} ({e}). "
                "Is it running, and is CLAWSOME_URL correct?"
            ) from None
    if response.is_error:
        raise ClawsomeError(_explain(response))
    return response


async def _json(method: str, path: str, **kw):
    response = await _request(method, path, **kw)
    return response.json() if response.content else None


@mcp.tool()
async def create_context(
    name: str,
    profile: str | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
) -> dict[str, Any]:
    """Create a browser context (one tab) and return its metadata, including its id.

    Args:
        name: short description of the task, shown on the dashboard.
        profile: saved login profile to use, or omit for a fresh session. A
            profile can only back one live context at a time.
        viewport_width: viewport width in pixels (default 1280).
        viewport_height: viewport height in pixels (default 720). Use a small
            size such as 390x844 to check a mobile layout.
    """
    body: dict = {"name": name}
    if profile:
        body["profile"] = profile
    if viewport_width and viewport_height:
        body["viewport"] = {"width": viewport_width, "height": viewport_height}
    meta = await _json("POST", "/api/contexts", json=body)
    return {**meta, "dashboard": f"{CLAWSOME_URL}/context/{meta['id']}"}


@mcp.tool()
async def list_contexts() -> list[dict[str, Any]]:
    """List the browser contexts that are currently alive."""
    return await _json("GET", "/api/contexts")


@mcp.tool()
async def goto(context_id: str, url: str, timeout: int | None = None) -> dict[str, Any]:
    """Navigate a context to a URL. Returns the resulting page url and title.

    Args:
        context_id: id returned by create_context.
        url: absolute URL to open.
        timeout: milliseconds to wait for navigation.
    """
    body: dict = {"url": url}
    if timeout:
        body["timeout"] = timeout
    return await _json("POST", f"/api/contexts/{context_id}/goto", json=body)


@mcp.tool()
async def snapshot(context_id: str) -> dict[str, Any]:
    """Read the current page: url, title, visible text, and interactive elements.

    Each element comes with a `selector` that can be passed straight to act().
    Take a snapshot after navigating instead of guessing selectors — it is
    cheaper than a failed action and a retry.
    """
    return await _json("GET", f"/api/contexts/{context_id}/snapshot")


@mcp.tool()
async def act(
    context_id: str,
    action: str,
    selector: str | None = None,
    value: str | None = None,
    script: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Perform an action on the page. Returns the page's resulting url and title.

    Args:
        context_id: id returned by create_context.
        action: one of click, type, select, wait, scroll, press, hover, back,
            reload, evaluate, waitForNavigation.
        selector: CSS selector the action applies to. For scroll, scrolls that
            element into view. For waitForNavigation, a URL glob to wait for.
        value: text for type, option for select, key name for press (e.g.
            "Enter"), or for scroll a pixel delta or one of top, bottom, page,
            -page.
        script: JavaScript to run, for the evaluate action.
        timeout: milliseconds to wait before giving up.

    Screenshots only capture the visible viewport, so scroll before capturing
    anything below the fold. If a click opens a new tab, the context follows it.
    """
    body: dict = {"action": action}
    for key, val in (("selector", selector), ("value", value),
                     ("script", script), ("timeout", timeout)):
        if val is not None:
            body[key] = val
    return await _json("POST", f"/api/contexts/{context_id}/exec", json=body)


@mcp.tool()
async def screenshot(context_id: str) -> Image:
    """Capture what the page looks like right now, as a PNG."""
    response = await _request("GET", f"/api/contexts/{context_id}/screenshot")
    return Image(data=response.content, format="png")


@mcp.tool()
async def log(context_id: str, message: str, level: str = "info") -> str:
    """Record a progress note against a context, so the user can follow along
    on the dashboard. Levels: info, warn, error."""
    await _json(
        "POST", f"/api/contexts/{context_id}/logs",
        json={"level": level, "message": message},
    )
    return "logged"


@mcp.tool()
async def destroy_context(context_id: str) -> str:
    """Destroy a context and free its browser page. Always do this when done."""
    await _json("DELETE", f"/api/contexts/{context_id}")
    return "destroyed"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""End-to-end test of the MCP server.

Drives it over real stdio transport with an MCP client, which in turn drives a
real Clawsome server and a real browser. Skipped when the optional `mcp` extra
is not installed.
"""

import os
import sys

import pytest

pytest.importorskip("mcp", reason="the optional 'mcp' extra is not installed")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from conftest import ROOT  # noqa: E402


@pytest.fixture
async def mcp_session(server, site):
    """An MCP client connected to the server, pointed at the test instance."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=str(ROOT),
        env={**os.environ, "CLAWSOME_URL": server},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def text_of(result):
    return "".join(c.text for c in result.content if getattr(c, "text", None))


@pytest.mark.anyio
async def test_tools_are_advertised(mcp_session):
    names = {t.name for t in (await mcp_session.list_tools()).tools}
    assert {"create_context", "goto", "act", "snapshot", "screenshot",
            "log", "destroy_context", "list_contexts"} <= names
    # Descriptions matter: they are what an agent reads to choose a tool.
    tools = {t.name: t for t in (await mcp_session.list_tools()).tools}
    assert tools["snapshot"].description
    assert "selector" in tools["snapshot"].description


@pytest.mark.anyio
async def test_a_whole_task_through_mcp(mcp_session, site):
    """Create, navigate, read the page, act on it, and clean up — via MCP."""
    created = await mcp_session.call_tool("create_context", {"name": "via-mcp"})
    assert not created.isError, text_of(created)
    ctx_id = created.structuredContent["id"]
    assert created.structuredContent["dashboard"].endswith(f"/context/{ctx_id}")

    try:
        moved = await mcp_session.call_tool(
            "goto", {"context_id": ctx_id, "url": f"{site}/index.html"})
        assert not moved.isError, text_of(moved)
        assert moved.structuredContent["title"] == "Clawsome Test Page"

        snap = await mcp_session.call_tool("snapshot", {"context_id": ctx_id})
        assert not snap.isError, text_of(snap)
        elements = snap.structuredContent["elements"]
        link = next(e for e in elements if e["label"] == "More info")

        # A selector straight from snapshot must work in act().
        acted = await mcp_session.call_tool(
            "act", {"context_id": ctx_id, "action": "click",
                    "selector": link["selector"]})
        assert not acted.isError, text_of(acted)

        after = await mcp_session.call_tool(
            "act", {"context_id": ctx_id, "action": "evaluate",
                    "script": "document.title"})
        assert after.structuredContent["result"] == "Second Page"

        logged = await mcp_session.call_tool(
            "log", {"context_id": ctx_id, "message": "did the thing"})
        assert not logged.isError
    finally:
        gone = await mcp_session.call_tool(
            "destroy_context", {"context_id": ctx_id})
        assert not gone.isError, text_of(gone)


@pytest.mark.anyio
async def test_screenshot_comes_back_as_an_image(mcp_session, site):
    created = await mcp_session.call_tool("create_context", {"name": "shot"})
    ctx_id = created.structuredContent["id"]
    try:
        await mcp_session.call_tool(
            "goto", {"context_id": ctx_id, "url": f"{site}/index.html"})
        shot = await mcp_session.call_tool("screenshot", {"context_id": ctx_id})
        assert not shot.isError, text_of(shot)
        image = next(c for c in shot.content if c.type == "image")
        assert image.mimeType == "image/png"
        assert len(image.data) > 100
    finally:
        await mcp_session.call_tool("destroy_context", {"context_id": ctx_id})


@pytest.mark.anyio
async def test_browser_failures_are_reported_readably(mcp_session, site):
    """A timeout should reach the agent as prose, not a raw stack trace."""
    created = await mcp_session.call_tool("create_context", {"name": "failing"})
    ctx_id = created.structuredContent["id"]
    try:
        await mcp_session.call_tool(
            "goto", {"context_id": ctx_id, "url": f"{site}/index.html"})
        result = await mcp_session.call_tool(
            "act", {"context_id": ctx_id, "action": "click",
                    "selector": "#not-there", "timeout": 800})
        assert result.isError
        message = text_of(result)
        assert "timeout" in message.lower()
        assert "#not-there" in message
    finally:
        await mcp_session.call_tool("destroy_context", {"context_id": ctx_id})


@pytest.mark.anyio
async def test_unknown_context_is_reported(mcp_session):
    result = await mcp_session.call_tool(
        "goto", {"context_id": "no-such-context", "url": "about:blank"})
    assert result.isError
    assert "not found" in text_of(result).lower()

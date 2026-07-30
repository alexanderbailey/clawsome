"""The liveness contract the dashboard's two live streams share.

A connection that dies without closing looks exactly like an idle one, so both
streams promise to send something on a known cadence and advertise that cadence
on connect. The client sizes its staleness threshold from what it is told,
which is only safe if the advertised number matches what the server actually
does — so these tests check the promise against the behaviour rather than
against a constant copied out of the server.
"""

import json
import time
import urllib.request

from websockets.sync.client import connect


def ws_url(client, path: str) -> str:
    return client.base.replace("http://", "ws://", 1) + path


def first_sse_event(base: str, timeout: float = 10.0) -> tuple[str, dict]:
    """Read the first complete event off the updates stream."""
    with urllib.request.urlopen(base + "/sse/updates", timeout=timeout) as r:
        event, data = None, None
        for _ in range(20):
            line = r.readline().decode().strip()
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())
            if event and data is not None:
                return event, data
    raise AssertionError("no complete event arrived on /sse/updates")


def test_sse_opens_with_a_ping_advertising_its_cadence(client):
    """Sizing the client's threshold needs a number, whatever the number is.

    The cadence itself is not exercised here: the stream only falls back to a
    keepalive after a long idle wait, and sitting through one would dominate
    the suite's runtime for little more assurance than the WebSocket case
    below already gives.
    """
    event, data = first_sse_event(client.base)
    assert event == "ping"
    assert isinstance(data.get("intervalMs"), int)
    assert data["intervalMs"] > 0


def test_screenshot_socket_advertises_the_cadence_it_actually_keeps(client):
    """The advertised interval has to describe real behaviour.

    An external context has no browser page to capture and no uploaded frame,
    so the server has nothing to send — the case that makes frame silence
    useless on its own as a dead-connection signal. It must still speak on the
    cadence it promised, or a client watching for silence tears down a healthy
    socket and reconnects forever.
    """
    meta = client.create_context(name="no-frames-yet", external=True)
    try:
        with connect(ws_url(client, f"/ws/screenshots/{meta['id']}")) as ws:
            opening = ws.recv(timeout=10)
            assert isinstance(opening, str), "the opening keepalive is text, not a frame"
            advertised = json.loads(opening)
            assert advertised["type"] == "ping"
            interval = advertised["intervalMs"] / 1000
            assert interval > 0

            # Three more keepalives, each inside the interval it claimed. The
            # client allows a generous multiple of this; anything near it here
            # would still be a broken promise.
            for _ in range(3):
                started = time.time()
                message = ws.recv(timeout=interval * 4)
                waited = time.time() - started
                assert isinstance(message, str), "no frame exists to send"
                assert json.loads(message)["type"] == "ping"
                assert waited <= interval * 2, (
                    f"waited {waited:.2f}s for a keepalive on a {interval:.2f}s cadence")
    finally:
        client.delete(f"/api/contexts/{meta['id']}")


def test_screenshot_socket_still_sends_frames(client, ctx, site):
    """Keepalives must not have displaced the actual screenshots."""
    client.goto(ctx["id"], f"{site}/index.html")
    with connect(ws_url(client, f"/ws/screenshots/{ctx['id']}")) as ws:
        deadline = time.time() + 20
        while time.time() < deadline:
            message = ws.recv(timeout=20)
            if isinstance(message, bytes):
                assert message.startswith(b"\x89PNG"), "frames are PNG"
                return
    raise AssertionError("no frame arrived on a context with a live page")


def test_screenshot_socket_closes_cleanly_when_the_context_goes_away(client, site):
    """Code 1000 is what tells the client to stop reconnecting for good."""
    meta = client.create_context(name="going-away")
    client.goto(meta["id"], f"{site}/index.html")
    with connect(ws_url(client, f"/ws/screenshots/{meta['id']}")) as ws:
        ws.recv(timeout=10)  # opening ping
        client.delete(f"/api/contexts/{meta['id']}")
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                ws.recv(timeout=20)
            except Exception:
                break
        assert ws.close_code == 1000, f"closed with {ws.close_code}, not a clean 1000"

"""Screenshot history is captured server-side, with no dashboard watching.

Nothing in this file opens the dashboard, a screenshot WebSocket, or the GET
screenshot endpoint — the frames have to arrive on the server's own initiative.
"""

import pytest

from conftest import Client, start_server, stop_server


@pytest.fixture(scope="module")
def capture_server():
    """A server with a brisk capture interval, so tests don't wait long."""
    proc, base = start_server({"CLAWSOME_CAPTURE_INTERVAL": "1"})
    yield base
    stop_server(proc)


@pytest.fixture
def capture_client(capture_server):
    return Client(capture_server)


def shots(client, ctx_id):
    status, saved = client.get(f"/api/contexts/{ctx_id}/screenshots")
    assert status == 200
    return saved


def test_navigating_records_a_frame_without_any_viewer(capture_client, site):
    ctx = capture_client.create_context(name="unwatched")
    try:
        assert shots(capture_client, ctx["id"]) == []
        capture_client.goto(ctx["id"], f"{site}/index.html")
        # The per-action capture is scheduled, not awaited, so give it a moment.
        saved = eventually_nonempty(capture_client, ctx["id"])
        assert saved, "navigating recorded no frame"
    finally:
        capture_client.delete(f"/api/contexts/{ctx['id']}")


def test_actions_add_frames_as_the_page_changes(capture_client, site):
    ctx = capture_client.create_context(name="stepping")
    try:
        capture_client.goto(ctx["id"], f"{site}/index.html")
        eventually_nonempty(capture_client, ctx["id"])
        before = len(shots(capture_client, ctx["id"]))

        # Each step changes the page, so each should leave a distinct frame.
        capture_client.exec(ctx["id"], action="scroll", value="bottom")
        capture_client.exec(ctx["id"], action="click", selector="#more-link")
        after = eventually_more_than(capture_client, ctx["id"], before)
        assert after > before, f"frames did not grow: {before} -> {after}"
    finally:
        capture_client.delete(f"/api/contexts/{ctx['id']}")


def test_history_survives_the_context_being_destroyed(capture_client, site):
    ctx = capture_client.create_context(name="outlives-me")
    capture_client.goto(ctx["id"], f"{site}/index.html")
    eventually_nonempty(capture_client, ctx["id"])
    saved = shots(capture_client, ctx["id"])
    capture_client.delete(f"/api/contexts/{ctx['id']}")

    still_there = shots(capture_client, ctx["id"])
    assert len(still_there) >= len(saved)
    status, body = capture_client.get(
        f"/api/contexts/{ctx['id']}/screenshots/{still_there[0]['filename']}")
    assert status == 200 and body[:8] == b"\x89PNG\r\n\x1a\n"


def test_an_idle_page_does_not_pile_up_duplicates(capture_client, site):
    """The periodic loop must not defeat the hash dedup from #26."""
    ctx = capture_client.create_context(name="idle")
    try:
        capture_client.goto(ctx["id"], f"{site}/index.html")
        eventually_nonempty(capture_client, ctx["id"])
        settled = len(shots(capture_client, ctx["id"]))
        import time
        time.sleep(4)  # several capture intervals with nothing changing
        assert len(shots(capture_client, ctx["id"])) == settled
    finally:
        capture_client.delete(f"/api/contexts/{ctx['id']}")


@pytest.fixture(scope="module")
def no_capture_client():
    proc, base = start_server({"CLAWSOME_CAPTURE_INTERVAL": "0"})
    yield Client(base)
    stop_server(proc)


def test_capture_can_be_switched_off(no_capture_client, site):
    """CLAWSOME_CAPTURE_INTERVAL=0 restores the old viewer-only behaviour.

    This is also what proves the frames in the tests above come from the new
    server-side capture: the identical flow records nothing when it is off.
    """
    import time
    ctx = no_capture_client.create_context(name="no-capture")
    try:
        no_capture_client.goto(ctx["id"], f"{site}/index.html")
        no_capture_client.exec(ctx["id"], action="scroll", value="bottom")
        time.sleep(3)
        assert shots(no_capture_client, ctx["id"]) == []

        # A viewer asking for a screenshot still records one, as before.
        assert no_capture_client.get(
            f"/api/contexts/{ctx['id']}/screenshot")[0] == 200
        assert shots(no_capture_client, ctx["id"])
    finally:
        no_capture_client.delete(f"/api/contexts/{ctx['id']}")


def test_external_contexts_are_left_alone(capture_client):
    """They push their own frames; the loop must not try to screenshot them."""
    ctx = capture_client.create_context(name="external", external=True)
    try:
        import time
        time.sleep(2.5)
        assert shots(capture_client, ctx["id"]) == []
        status, listing = capture_client.get("/api/contexts")
        assert ctx["id"] in [c["id"] for c in listing], "context was disturbed"
    finally:
        capture_client.delete(f"/api/contexts/{ctx['id']}")


# -- small polling helpers ------------------------------------------------

def eventually_nonempty(client, ctx_id, timeout=10.0):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        saved = shots(client, ctx_id)
        if saved:
            return saved
        time.sleep(0.25)
    return []


def eventually_more_than(client, ctx_id, count, timeout=10.0):
    import time
    deadline = time.time() + timeout
    seen = count
    while time.time() < deadline:
        seen = len(shots(client, ctx_id))
        if seen > count:
            return seen
        time.sleep(0.25)
    return seen

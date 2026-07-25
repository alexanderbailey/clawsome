"""The dashboard pages a human actually looks at."""


def test_root_redirects_to_summary(client):
    status, _ = client.get("/summary")
    assert status == 200


def test_summary_shows_an_empty_state_then_a_tile(client):
    status, html = client.get("/partials/context-list")
    assert status == 200
    assert b"No active browser contexts" in html

    meta = client.create_context(name="on-the-dashboard")
    try:
        _, html = client.get("/partials/context-list")
        assert f"ctx-{meta['id']}".encode() in html
        assert b"on-the-dashboard" in html
    finally:
        client.delete(f"/api/contexts/{meta['id']}")


def test_context_page_renders_for_a_live_context(client, ctx):
    status, html = client.get(f"/context/{ctx['id']}")
    assert status == 200
    assert b"fixture-context" in html
    assert b"badge-running" in html


def test_context_page_renders_after_it_stops(client, site):
    meta = client.create_context(name="stopped-one")
    client.goto(meta["id"], f"{site}/index.html")
    client.get(f"/api/contexts/{meta['id']}/screenshot")  # save a frame
    client.delete(f"/api/contexts/{meta['id']}")

    status, html = client.get(f"/context/{meta['id']}")
    assert status == 200
    assert b"badge-stopped" in html


def test_unknown_context_page_is_404(client):
    assert client.get("/context/does-not-exist")[0] == 404


def test_history_lists_stopped_contexts(client):
    meta = client.create_context(name="for-history")
    client.delete(f"/api/contexts/{meta['id']}")

    status, html = client.get("/history")
    assert status == 200
    assert b"for-history" in html
    # History links carry their origin so the back link can return here.
    assert f"/context/{meta['id']}?from=history".encode() in html


def test_back_link_follows_where_you_came_from(client, ctx):
    _, from_summary = client.get(f"/context/{ctx['id']}")
    assert b'href="/summary"' in from_summary
    assert b"Back to summary" in from_summary

    _, from_history = client.get(f"/context/{ctx['id']}?from=history")
    assert b'href="/history"' in from_history
    assert b"Back to history" in from_history

    # The origin is threaded onward to the logs page too.
    assert f"/logs/{ctx['id']}?from=history".encode() in from_history


def test_an_unknown_origin_falls_back_to_summary(client, ctx):
    _, html = client.get(f"/context/{ctx['id']}?from=elsewhere")
    assert b'href="/summary"' in html


def test_logs_page_renders_entries(client, ctx):
    client.post(f"/api/contexts/{ctx['id']}/logs", {"message": "a logged line"})
    status, html = client.get(f"/logs/{ctx['id']}")
    assert status == 200
    assert b"a logged line" in html

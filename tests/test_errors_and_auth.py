"""Structured failures, the profile lock, and bearer-token auth."""

import shutil

from conftest import ROOT, Client


def test_navigation_failure_is_a_structured_400(client, ctx):
    # Port 9 is reserved and refused, so this fails inside the browser.
    status, body = client.goto(ctx["id"], "http://127.0.0.1:9/nope", timeout=5000)
    assert status == 400, body
    assert body["error"] == "navigation"
    assert body["message"]
    assert "url" in body


def test_missing_selector_is_a_timeout_error(client, ctx, site):
    client.goto(ctx["id"], f"{site}/index.html")
    status, body = client.exec(
        ctx["id"], action="click", selector="#nothing-here", timeout=800)
    assert status == 400
    assert body["error"] == "timeout"
    assert "#nothing-here" in body["message"]
    assert body["url"] == f"{site}/index.html"


def test_script_error_is_reported(client, ctx, site):
    client.goto(ctx["id"], f"{site}/index.html")
    status, body = client.exec(
        ctx["id"], action="evaluate", script="throw new Error('boom')")
    assert status == 400
    assert body["error"] == "error"
    assert "boom" in body["message"]


def test_actions_on_an_unknown_context_are_404(client):
    assert client.goto("nope", "about:blank")[0] == 404
    assert client.get("/api/contexts/nope/snapshot")[0] == 404


def test_a_failure_is_written_to_the_context_log(client, ctx, site):
    client.goto(ctx["id"], f"{site}/index.html")
    client.exec(ctx["id"], action="click", selector="#nothing-here", timeout=500)
    status, logs = client.get(f"/api/contexts/{ctx['id']}/logs")
    assert status == 200
    assert any(entry["level"] == "error" for entry in logs), logs


def test_logs_can_be_appended_and_read_back(client, ctx):
    assert client.post(f"/api/contexts/{ctx['id']}/logs",
                       {"level": "warn", "message": "something happened"})[0] == 201
    _, logs = client.get(f"/api/contexts/{ctx['id']}/logs")
    assert any(e["message"] == "something happened" and e["level"] == "warn"
               for e in logs)


def test_screenshots_are_saved_and_listed(client, ctx, site):
    client.goto(ctx["id"], f"{site}/index.html")
    status, png = client.get(f"/api/contexts/{ctx['id']}/screenshot")
    assert status == 200
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    status, saved = client.get(f"/api/contexts/{ctx['id']}/screenshots")
    assert status == 200 and saved, saved
    status, body = client.get(
        f"/api/contexts/{ctx['id']}/screenshots/{saved[0]['filename']}")
    assert status == 200
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


def test_screenshot_path_traversal_is_blocked(client, ctx):
    for name in ("../../pyproject.toml", "..%2f..%2fpyproject.toml",
                 "/etc/hostname", "nested/shot.png", "missing.png"):
        status, _ = client.get(f"/api/contexts/{ctx['id']}/screenshots/{name}")
        assert status == 404, name


def test_a_profile_can_only_back_one_context(client):
    """The second context using a live profile gets a clear 409, not a 500."""
    name = "e2e-profile"
    profile = ROOT / "profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    try:
        first = client.create_context(name="holder", profile=name)
        try:
            assert first["persistent"] is True
            status, body = client.post(
                "/api/contexts", {"name": "second", "profile": name})
            assert status == 409, body
            assert body["error"] == "profile_in_use"
            assert first["id"] in body["message"]
        finally:
            client.delete(f"/api/contexts/{first['id']}")

        # Released on destroy, so the profile is usable again.
        again = client.create_context(name="third", profile=name)
        client.delete(f"/api/contexts/{again['id']}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def test_token_auth(token_server):
    base, token = token_server
    anon, authed = Client(base), Client(base, token)

    assert anon.get("/api/contexts")[0] == 401
    assert Client(base, "wrong-token").get("/api/contexts")[0] == 401
    assert authed.get("/api/contexts")[0] == 200

    # /health and the dashboard stay open by design.
    assert anon.get("/health")[0] == 200


def test_token_is_not_required_by_default(client):
    assert client.get("/api/contexts")[0] == 200

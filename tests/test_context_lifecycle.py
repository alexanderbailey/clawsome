"""Context creation, metadata, listing and teardown."""


def test_health(client):
    assert client.get("/health") == (200, {"status": "ok"})


def test_create_returns_metadata_and_appears_in_list(client):
    meta = client.create_context(name="lifecycle")
    try:
        assert meta["name"] == "lifecycle"
        assert meta["external"] is False
        assert meta["viewport"] == {"width": 1280, "height": 720}
        assert meta["created_at"] and meta["last_activity"]

        status, listing = client.get("/api/contexts")
        assert status == 200
        assert meta["id"] in [c["id"] for c in listing]
    finally:
        client.delete(f"/api/contexts/{meta['id']}")


def test_destroy_removes_it_from_the_list(client):
    meta = client.create_context()
    assert client.delete(f"/api/contexts/{meta['id']}") == (200, {"ok": True})

    _, listing = client.get("/api/contexts")
    assert meta["id"] not in [c["id"] for c in listing]
    assert client.get(f"/api/contexts/{meta['id']}")[0] == 404


def test_unknown_context_is_404(client):
    assert client.get("/api/contexts/does-not-exist")[0] == 404
    assert client.delete("/api/contexts/does-not-exist")[0] == 404


def test_custom_viewport_is_applied_to_the_page(client, site):
    meta = client.create_context(name="mobile", viewport={"width": 390, "height": 844})
    try:
        assert meta["viewport"] == {"width": 390, "height": 844}
        client.goto(meta["id"], f"{site}/index.html")
        status, result = client.exec(
            meta["id"], action="evaluate",
            script="({w: window.innerWidth, h: window.innerHeight})")
        assert status == 200
        assert result["result"] == {"w": 390, "h": 844}
    finally:
        client.delete(f"/api/contexts/{meta['id']}")


def test_invalid_viewport_is_rejected(client):
    for viewport in ({"width": 0, "height": 844},
                     {"width": 390, "height": -5},
                     {"width": 99999, "height": 844},
                     {"width": 390}):
        status, _ = client.post("/api/contexts", {"name": "bad", "viewport": viewport})
        assert status == 422, viewport


def test_external_context_has_no_browser_page(client):
    meta = client.create_context(name="external", external=True)
    try:
        assert meta["external"] is True
        assert meta["viewport"] is None
        # Screenshots are pushed in rather than captured.
        status, _ = client.post(f"/api/contexts/{meta['id']}/screenshot",
                                raw=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
                                content_type="image/png")
        assert status == 204
        assert client.get(f"/api/contexts/{meta['id']}/screenshot")[0] == 200
    finally:
        client.delete(f"/api/contexts/{meta['id']}")

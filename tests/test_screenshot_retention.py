"""Saved screenshots are capped and aged out, so the disk stops growing.

Frames are uploaded to external contexts rather than captured from a browser:
retention is about which files exist, and uploading gives each test exact
control over how many frames there are and what is in them.
"""

import tempfile
import time
from pathlib import Path

import pytest

from conftest import Client, start_server, stop_server

PNG = b"\x89PNG\r\n\x1a\n"
DAY_MS = 86_400_000


def frame(n: int) -> bytes:
    """A distinct payload per frame, so the dedup in #26 doesn't swallow it."""
    return PNG + f"frame-{n}".encode()


def upload(client, ctx_id, n):
    status, _ = client.post(f"/api/contexts/{ctx_id}/screenshot", raw=frame(n),
                            content_type="image/png")
    assert status == 204, status
    # Filenames are millisecond timestamps; don't let two frames collide on one.
    time.sleep(0.01)


def saved(client, ctx_id) -> list[dict]:
    status, listing = client.get(f"/api/contexts/{ctx_id}/screenshots")
    assert status == 200
    return listing


def contents(client, ctx_id) -> list[bytes]:
    """The bytes of every surviving frame, newest first."""
    out = []
    for s in saved(client, ctx_id):
        status, body = client.get(
            f"/api/contexts/{ctx_id}/screenshots/{s['filename']}")
        assert status == 200
        out.append(body)
    return out


def write_stale(shots_dir: Path, ctx_id: str, age_days: int, count: int) -> list[Path]:
    """Plant frames dated in the past, as a long-running instance would have."""
    d = shots_dir / ctx_id
    d.mkdir(parents=True, exist_ok=True)
    now_ms = int(time.time() * 1000)
    written = []
    for i in range(count):
        f = d / f"{now_ms - age_days * DAY_MS - i}.png"
        f.write_bytes(frame(1000 + i))
        written.append(f)
    return written


@pytest.fixture(scope="module")
def retention():
    """A server keeping three frames per context, with the default max age."""
    data = tempfile.mkdtemp(prefix="clawsome-retention-")
    proc, base = start_server({
        "CLAWSOME_DATA_DIR": data,
        "CLAWSOME_SCREENSHOT_LIMIT": "3",
        "CLAWSOME_CAPTURE_INTERVAL": "0",  # no browser frames to confuse counts
    })
    yield Client(base), Path(data) / "screenshots"
    stop_server(proc)


def test_the_cap_keeps_the_newest_frames(retention):
    client, _ = retention
    ctx = client.create_context(name="capped", external=True)
    try:
        for n in range(6):
            upload(client, ctx["id"], n)
        assert len(saved(client, ctx["id"])) == 3
        assert contents(client, ctx["id"]) == [frame(5), frame(4), frame(3)]
    finally:
        client.delete(f"/api/contexts/{ctx['id']}")


def test_old_frames_are_deleted_when_a_new_one_arrives(retention):
    client, shots_dir = retention
    ctx = client.create_context(name="ageing", external=True)
    try:
        write_stale(shots_dir, ctx["id"], age_days=30, count=2)
        assert len(saved(client, ctx["id"])) == 2

        upload(client, ctx["id"], 0)
        # Only the fresh frame survives — the cap alone would have kept all three.
        assert contents(client, ctx["id"]) == [frame(0)]
    finally:
        client.delete(f"/api/contexts/{ctx['id']}")


def test_a_stopped_context_is_swept_on_startup():
    """Nothing writes to a stopped context, so ageing it out needs the sweep."""
    data = Path(tempfile.mkdtemp(prefix="clawsome-sweep-"))
    stale = write_stale(data / "screenshots", "long-finished", age_days=30, count=3)
    assert all(f.exists() for f in stale)

    proc, _base = start_server({"CLAWSOME_DATA_DIR": str(data)})
    try:
        # The sweep is a background task, so it may land just after startup.
        deadline = time.time() + 10
        while any(f.exists() for f in stale) and time.time() < deadline:
            time.sleep(0.1)
        assert not any(f.exists() for f in stale)
        # The now-empty directory goes too, rather than lingering forever.
        assert not (data / "screenshots" / "long-finished").exists()
    finally:
        stop_server(proc)


@pytest.fixture(scope="module")
def unlimited():
    data = tempfile.mkdtemp(prefix="clawsome-unlimited-")
    proc, base = start_server({
        "CLAWSOME_DATA_DIR": data,
        "CLAWSOME_SCREENSHOT_LIMIT": "0",
        "CLAWSOME_SCREENSHOT_MAX_AGE_DAYS": "0",
        "CLAWSOME_CAPTURE_INTERVAL": "0",
    })
    yield Client(base), Path(data) / "screenshots"
    stop_server(proc)


def test_retention_can_be_switched_off(unlimited):
    client, shots_dir = unlimited
    ctx = client.create_context(name="keep-everything", external=True)
    try:
        stale = write_stale(shots_dir, ctx["id"], age_days=30, count=2)
        for n in range(6):
            upload(client, ctx["id"], n)
        assert len(saved(client, ctx["id"])) == 8
        assert all(f.exists() for f in stale)
    finally:
        client.delete(f"/api/contexts/{ctx['id']}")

"""Shared fixtures for the end-to-end suite.

These tests drive a real Clawsome server over HTTP, which drives a real
headless Chromium, against a real (locally served) web page. Nothing is
mocked, so a passing run means the whole stack works together.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PAGES = Path(__file__).parent / "pages"
STARTUP_TIMEOUT = 90  # a cold start also launches Chromium


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    """Minimal HTTP client for the API, so the suite has no extra dependency."""

    def __init__(self, base: str, token: str | None = None):
        self.base = base
        self.token = token

    def request(self, method: str, path: str, body=None, raw: bytes | None = None,
                content_type: str | None = None):
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None)
        headers = {}
        if data is not None:
            headers["Content-Type"] = content_type or "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                payload = r.read()
                return r.status, self._decode(payload)
        except urllib.error.HTTPError as e:
            return e.code, self._decode(e.read())

    @staticmethod
    def _decode(payload: bytes):
        if not payload:
            return None
        try:
            return json.loads(payload)
        except ValueError:
            return payload

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)

    def delete(self, path):
        return self.request("DELETE", path)

    # -- convenience ------------------------------------------------------
    def create_context(self, **body):
        body.setdefault("name", "test")
        status, meta = self.post("/api/contexts", body)
        assert status == 201, (status, meta)
        return meta

    def exec(self, ctx_id, **body):
        return self.post(f"/api/contexts/{ctx_id}/exec", body)

    def goto(self, ctx_id, url, **body):
        return self.post(f"/api/contexts/{ctx_id}/goto", {"url": url, **body})


def _start_server(env_extra: dict[str, str]) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    env = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port), **env_extra}
    # Each server gets its own data dir so runs cannot interfere with a
    # developer's real database or with each other.
    env.setdefault("CLAWSOME_DATA_DIR", tempfile.mkdtemp(prefix="clawsome-test-"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.app"], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                "server exited during startup:\n"
                + proc.stdout.read().decode(errors="replace"))
        try:
            urllib.request.urlopen(base + "/health", timeout=1)
            return proc, base
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("server did not become healthy in time")


def _stop_server(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def eventually(fn, expected, timeout: float = 5.0, interval: float = 0.05):
    """Poll until fn() equals expected, then return it (or the last value seen).

    A few things settle asynchronously in the browser — most notably a tab
    opened by a click, which the browser reports a moment after the click
    itself returns. Polling keeps those tests honest without making them flaky.
    """
    deadline = time.time() + timeout
    value = fn()
    while value != expected and time.time() < deadline:
        time.sleep(interval)
        value = fn()
    return value


@pytest.fixture(scope="session")
def site() -> str:
    """A local static site, so tests never depend on the public internet."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(PAGES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def server():
    proc, base = _start_server({})
    yield base
    _stop_server(proc)


@pytest.fixture
def client(server) -> Client:
    return Client(server)


@pytest.fixture
def ctx(client):
    """A browser context that is destroyed even if the test fails."""
    meta = client.create_context(name="fixture-context")
    yield meta
    client.delete(f"/api/contexts/{meta['id']}")


@pytest.fixture(scope="session")
def token_server():
    """A second server with bearer-token auth enabled."""
    token = "test-token-value"
    proc, base = _start_server({"CLAWSOME_TOKEN": token})
    yield base, token
    _stop_server(proc)

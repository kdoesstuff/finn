"""The service as Render runs it: render.yaml's own start command, environment and health check,
in a real uvicorn process over real HTTP (h11), against the scratch database.

This is what in-process tests cannot show: that the start command works from the repository root
with PYTHONPATH=pipeline, that uvicorn sends no Server header, that the body limit holds against
a real chunked upload, and that the process starts without a database and stops cleanly."""

from __future__ import annotations

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Any

import pytest

from api.tests.helpers import CORE, ROOT, SECRET
from tests.dbtools import admin_url

BLUEPRINT = (ROOT / "render.yaml").read_text(encoding="utf-8")


def blueprint(key: str) -> str:
    match = re.search(rf"^\s+{key}: (.+)$", BLUEPRINT, re.MULTILINE)
    assert match, f"render.yaml has no {key}"
    return match.group(1).strip()


def env_value(key: str) -> str:
    match = re.search(rf"- key: {key}\n\s+value: (.+)", BLUEPRINT)
    assert match, f"render.yaml sets no value for {key}"
    return match.group(1).strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def request(port: int, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None,
            chunked: bool = False) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


def wait_healthy(port: int, proc: subprocess.Popen[str], limit_s: float = 30.0) -> float:
    started = time.monotonic()
    while time.monotonic() - started < limit_s:
        if proc.poll() is not None:
            raise AssertionError(f"the server exited: {proc.communicate()[1]}")
        try:
            if request(port, "GET", "/health")[0] == 200:
                return time.monotonic() - started
        except OSError:
            time.sleep(0.1)
    raise AssertionError("the server did not answer /health")


def start(database_url: str) -> tuple[subprocess.Popen[str], int]:
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SUPABASE", "SENTRY", "RENDER"))}
    env.update({"PORT": str(port), "PYTHONPATH": env_value("PYTHONPATH"), "SUPABASE_DB_URL": database_url,
                "SESSION_SECRET": SECRET.decode(), "ALLOWED_ORIGINS_CORE": CORE,
                # uvicorn from the environment running these tests, as Render's build puts it on PATH
                "PATH": os.pathsep.join([os.path.dirname(sys.executable), env.get("PATH", "")])})
    # The command line exactly as render.yaml has it; Render runs it in a shell, so $PORT expands.
    proc = subprocess.Popen(["/bin/sh", "-c", f"exec {blueprint('startCommand')}"], cwd=ROOT, env=env,  # noqa: S603
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc, port


def stop(proc: subprocess.Popen[str]) -> tuple[int, str]:
    """SIGTERM, as Render sends on a deploy or a spin-down; returns the exit code and the logs.
    Uvicorn shuts down gracefully and then re-raises the signal, so a clean stop exits -SIGTERM."""
    proc.send_signal(signal.SIGTERM)
    try:
        _, logs = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, logs = proc.communicate()
    return proc.returncode, logs


def stopped_cleanly(code: int, logs: str) -> bool:
    return code in (0, -signal.SIGTERM) and "Application shutdown complete" in logs


@pytest.fixture
def server(database: str, admin: Any) -> Iterator[int]:
    proc, port = start(admin_url(database))
    try:
        wait_healthy(port, proc)
        yield port
    finally:
        code, logs = stop(proc)
    assert stopped_cleanly(code, logs), logs


def test_the_blueprint_is_what_this_test_runs():
    assert blueprint("healthCheckPath") == "/health"
    assert blueprint("startCommand").startswith("uvicorn api.main:app --host 0.0.0.0 --port $PORT")
    assert re.fullmatch(r"3\.12\.\d+", env_value("PYTHON_VERSION"))


def test_the_service_answers_over_real_http(server):
    status, headers, body = request(server, "GET", "/health")
    assert status == 200 and json.loads(body)["db"] is True
    assert "server" not in headers and headers["strict-transport-security"].startswith("max-age=")

    status, headers, body = request(server, "POST", "/v1/session/demo", headers={"Origin": CORE})
    assert status == 200 and headers["access-control-allow-origin"] == CORE
    token = json.loads(body)["token"]

    status, _, body = request(server, "GET", "/v1/digest?hours=744", headers={"Authorization": f"Bearer {token}"})
    assert status == 200 and json.loads(body)["window"]["hours"] == 744

    big = (b"z" * 4096 for _ in range(5))  # 20 KB, sent chunked: no Content-Length to refuse it by
    status, _, body = request(server, "POST", "/v1/session/demo", body=big, headers={"Origin": CORE}, chunked=True)
    assert status == 413 and json.loads(body)["error"]["code"] == "bad_request"

    status, _, body = request(server, "GET", "/v1/digest/", headers={"X-Forwarded-Proto": "http"})
    assert status == 404 and json.loads(body)["error"]["code"] == "not_found"  # no redirect to http://


def test_the_service_starts_and_reports_health_with_no_database():
    proc, port = start("postgresql://nobody:not-a-real-password@127.0.0.1:1/none")
    try:
        wait_healthy(port, proc)
        status, _, body = request(port, "GET", "/health")
        assert status == 200 and json.loads(body)["db"] is False
    finally:
        code, logs = stop(proc)
    assert stopped_cleanly(code, logs), logs
    assert "not-a-real-password" not in logs

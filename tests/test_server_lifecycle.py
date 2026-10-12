"""The server started by VideoDownloader.app never outlives the app."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).parent.parent / "backend"

# A stand-in for the app: starts the server as its child, then waits on it forever.
PARENT = """
import os, subprocess, sys
env = dict(os.environ, VD_PARENT_PID=str(os.getpid()))
child = subprocess.Popen([sys.executable, "-m", "app.main"], env=env)
print(child.pid, flush=True)
child.wait()
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return bool(r.status == 200)
    except OSError:
        return False


def test_the_server_shuts_down_when_the_app_that_started_it_dies(tmp_path: Path) -> None:
    port = free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "VD_PORT": str(port),
        "VD_FIXTURE_MODE": "1",
        "VD_DATA_DIR": str(tmp_path / "data"),
        "VD_DOWNLOAD_DIR": str(tmp_path / "downloads"),
    }
    parent = subprocess.Popen(
        [sys.executable, "-c", PARENT], env=env, stdout=subprocess.PIPE, text=True
    )
    assert parent.stdout is not None
    server = int(parent.stdout.readline())
    try:
        deadline = time.monotonic() + 30
        while not healthy(port):
            assert time.monotonic() < deadline, "the server never came up"
            assert alive(server), "the server died on its own"
            time.sleep(0.1)

        parent.kill()  # the app crashes: no chance to stop its child
        parent.wait()
        deadline = time.monotonic() + 15
        while alive(server):
            assert time.monotonic() < deadline, "the orphaned server kept running"
            time.sleep(0.1)
        assert not healthy(port)
    finally:
        if alive(server):
            os.kill(server, signal.SIGKILL)


def post(port: int, path: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result: dict[str, object] = json.loads(response.read())
        return result


def children(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
    return [int(line) for line in out.split()]


def test_sigterm_stops_promptly_and_cleanly_even_with_an_open_event_stream(
    tmp_path: Path, media_server: str
) -> None:
    """The app's quit sends SIGTERM and SIGKILLs after 15 s. An open SSE connection used to hold
    uvicorn past that, so the clean shutdown -- the one that stops the download workers, which
    run in sessions of their own -- never ran, and a running download was left behind."""
    port = free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "VD_PORT": str(port),
        "VD_FIXTURE_MODE": "1",
        "VD_FIXTURE_MEDIA_BASE": f"{media_server}/slow",
        "VD_DATA_DIR": str(tmp_path / "data"),
        "VD_DOWNLOAD_DIR": str(tmp_path / "downloads"),
    }
    log = tmp_path / "server.log"
    server = subprocess.Popen(
        [sys.executable, "-m", "app.main"], env=env, stderr=log.open("w"), stdout=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 30
        while not healthy(port):
            assert time.monotonic() < deadline, "the server never came up"
            time.sleep(0.1)
        stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=10)
        assert stream.readline().startswith(b"retry:")  # the stream is open and stays open
        quick = post(
            port,
            "/api/quick",
            {"url": "https://example.test/local-media", "rule": {"kind": "video"}},
        )
        job_id = quick["job"]["id"]  # type: ignore[index]
        workers: list[int] = []
        deadline = time.monotonic() + 15
        while not workers:
            assert time.monotonic() < deadline, "the download never started"
            workers = children(server.pid)
            time.sleep(0.05)
        assert job_id

        started = time.monotonic()
        server.send_signal(signal.SIGTERM)
        code = server.wait(timeout=12)
        elapsed = time.monotonic() - started
        stream.close()
        # uvicorn re-raises the signal after its graceful shutdown: -SIGTERM is a clean exit.
        assert code in (0, -signal.SIGTERM), f"exit code {code}"
        # The streams are told to end at once: no waiting out uvicorn's 2 s limit.
        assert elapsed < 1.5, f"shutdown took {elapsed:.1f} s"
        assert "timeout graceful shutdown exceeded" not in log.read_text()
        deadline = time.monotonic() + 3
        while any(alive(w) for w in workers) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not [w for w in workers if alive(w)], "a download worker outlived the server"
    finally:
        if server.poll() is None:
            server.kill()


def test_workers_die_with_a_server_that_is_killed_outright(
    tmp_path: Path, media_server: str
) -> None:
    """SIGKILL (Force Quit, a crash, the app's 15 s fallback) skips every clean shutdown path.
    A worker that is writing progress dies of the broken pipe anyway; the silent case is below."""
    port = free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "VD_PORT": str(port),
        "VD_FIXTURE_MODE": "1",
        "VD_FIXTURE_MEDIA_BASE": f"{media_server}/slow",
        "VD_DATA_DIR": str(tmp_path / "data"),
        "VD_DOWNLOAD_DIR": str(tmp_path / "downloads"),
    }
    server = subprocess.Popen([sys.executable, "-m", "app.main"], env=env)
    workers: list[int] = []
    try:
        deadline = time.monotonic() + 30
        while not healthy(port):
            assert time.monotonic() < deadline, "the server never came up"
            time.sleep(0.1)
        body = {"url": "https://example.test/local-media", "rule": {"kind": "video"}}
        post(port, "/api/quick", body)
        deadline = time.monotonic() + 15
        while not workers:
            assert time.monotonic() < deadline, "the download never started"
            workers = children(server.pid)
            time.sleep(0.05)
        grandchildren = [g for w in workers for g in children(w)]

        server.kill()
        server.wait()
        deadline = time.monotonic() + 5
        everyone = workers + grandchildren
        while any(alive(p) for p in everyone) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not [p for p in everyone if alive(p)], "a worker outlived the killed server"
    finally:
        for pid in workers:
            if alive(pid):
                os.kill(pid, signal.SIGKILL)


# A worker as the server starts one (own session), silent, with a child of its own (FFmpeg).
SILENT_WORKER = """
import subprocess, sys, time
sys.path.insert(0, sys.argv[1])
from app.workers import lifeline
lifeline.hold()
child = subprocess.Popen(["sleep", "60"])
print(child.pid, flush=True)
time.sleep(60)
"""

# Stands in for the server: starts the worker, reports both pids, then waits to be killed.
FAKE_SERVER = """
import subprocess, sys
worker = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1], sys.argv[2]], stdout=subprocess.PIPE, text=True,
    start_new_session=True,
)
print(worker.pid, worker.stdout.readline().strip(), flush=True)
worker.wait()
"""


def test_a_silent_worker_and_its_children_die_when_the_server_is_killed() -> None:
    """The lifeline itself: a worker that writes nothing (a long FFmpeg mux) gets no broken
    pipe, and a signal to the server's group never reaches its session."""
    server = subprocess.Popen(
        [sys.executable, "-c", FAKE_SERVER, SILENT_WORKER, str(BACKEND)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert server.stdout is not None
    worker, grandchild = (int(x) for x in server.stdout.readline().split())
    try:
        assert alive(worker) and alive(grandchild)
        server.kill()
        server.wait()
        deadline = time.monotonic() + 5
        while (alive(worker) or alive(grandchild)) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(worker), "the worker outlived its server"
        assert not alive(grandchild), "the worker's child outlived the server"
    finally:
        for pid in (worker, grandchild):
            if alive(pid):
                os.kill(pid, signal.SIGKILL)

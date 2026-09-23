"""The shared job queue.

Each running job is one child process in its own process group: cancel kills the group (so
yt-dlp's FFmpeg and deno children die with it), and a crash in a job cannot reach the server.
State lives in SQLite, so the queue survives a restart; jobs that were running are requeued and
yt-dlp resumes their `.part` files from the same scratch directory.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import paths
from app.db import JobStore
from app.settings import Settings

CANCEL_GRACE_SECONDS = 5
PUBLIC_REQUEST_FIELDS = (
    "mode",
    "video_format_id",
    "audio_format_ids",
    "subtitle_keys",
    "audio_codec",
    "url",
)


def public(job: dict[str, Any]) -> dict[str, Any]:
    """What the UI sees: everything except the (possibly large) worker request."""
    request = job.get("request") or {}
    out = {k: v for k, v in job.items() if k != "request"}
    out["selection"] = {k: request.get(k) for k in PUBLIC_REQUEST_FIELDS}
    return out


class JobManager:
    def __init__(self, store: JobStore, get_settings: Callable[[], Settings]) -> None:
        self.store = store
        self.get_settings = get_settings
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        self.cancelling: set[str] = set()
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._wake = asyncio.Event()
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- lifecycle ------------------------------------------------------------------------
    async def start(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        self.store.requeue_interrupted()
        self._loop_task = asyncio.create_task(self._loop())
        self._wake.set()

    async def stop(self) -> None:
        self._publish_now({"type": "shutdown"})
        if self._loop_task:
            self._loop_task.cancel()
        # Interrupted jobs stay "running" in the database and are requeued on the next start.
        for job_id in list(self.procs):
            self._signal(job_id, signal.SIGTERM)
        for task in list(self._tasks):
            task.cancel()

    def _on_loop(self, fn: Callable[..., Any], *args: Any) -> None:
        """asyncio primitives are not thread-safe. Anything reaching the manager from another
        thread (a sync route, a test) is marshalled onto the manager's own loop."""
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if self._event_loop is None or current is self._event_loop:
            fn(*args)
        else:
            self._event_loop.call_soon_threadsafe(fn, *args)

    def wake(self) -> None:
        self._on_loop(self._wake.set)

    # ---- pub/sub for Server-Sent Events -----------------------------------------------------
    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        self._on_loop(self._publish_now, payload)

    def _publish_now(self, payload: dict[str, Any]) -> None:
        for queue in list(self.subscribers):
            with contextlib.suppress(asyncio.QueueFull):  # a stalled tab must not block others
                queue.put_nowait(payload)

    def _update(self, job_id: str, **changes: Any) -> dict[str, Any] | None:
        job = self.store.update(job_id, **changes)
        if job:
            self.publish({"type": "job", "job": public(job)})
        return job

    # ---- scheduling -----------------------------------------------------------------------
    async def _loop(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            free = self.get_settings().concurrency - len(self.procs)
            if free <= 0:
                continue
            for job in self.store.next_queued(free):
                # Mark it running *before* the task starts, so it cannot be picked twice.
                self._update(
                    job["id"],
                    status="running",
                    stage="starting",
                    started_at=time.time(),
                    error_code=None,
                    error_raw=None,
                )
                task = asyncio.create_task(self._run(job))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _run(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        env = dict(os.environ)
        backend_dir = str(paths.PROJECT_ROOT / "backend")
        env["PYTHONPATH"] = backend_dir + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        outcome: dict[str, Any] = {}
        stderr_tail: deque[str] = deque(maxlen=60)
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.workers.download_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(paths.PROJECT_ROOT),
                start_new_session=True,
                limit=1 << 20,
            )
        except OSError as exc:
            self._update(
                job_id,
                status="failed",
                stage="failed",
                error_code="WORKER_START_FAILED",
                error_raw=str(exc),
                finished_at=time.time(),
            )
            self.wake()
            return
        self.procs[job_id] = proc
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(json.dumps(job["request"]).encode())
        await proc.stdin.drain()
        proc.stdin.close()

        async def drain_stderr() -> None:
            assert proc.stderr
            async for raw in proc.stderr:
                stderr_tail.append(raw.decode(errors="replace").rstrip())

        stderr_task = asyncio.create_task(drain_stderr())
        try:
            async for raw in proc.stdout:
                try:
                    event = json.loads(raw)
                except ValueError:
                    stderr_tail.append(raw.decode(errors="replace").rstrip())
                    continue
                self._apply(job_id, event, outcome)
            await proc.wait()
            await stderr_task
        finally:
            self.procs.pop(job_id, None)
            if proc.returncode is None:
                self._signal_proc(proc, signal.SIGKILL)

        if job_id in self.cancelling:
            self.cancelling.discard(job_id)
            self._update(
                job_id,
                status="cancelled",
                stage="cancelled",
                speed=None,
                eta=None,
                finished_at=time.time(),
            )
        elif "files" in outcome:
            self._update(
                job_id,
                status="done",
                stage="done",
                progress=1.0,
                speed=None,
                eta=None,
                output_files=outcome["files"],
                finished_at=time.time(),
            )
        else:
            code = outcome.get("code") or "WORKER_CRASHED"
            detail = outcome.get("raw") or "\n".join(stderr_tail) or f"exit {proc.returncode}"
            self._update(
                job_id,
                status="failed",
                stage="failed",
                speed=None,
                eta=None,
                error_code=code,
                error_raw=str(detail)[-8000:],
                finished_at=time.time(),
            )
        self.wake()

    def _apply(self, job_id: str, event: dict[str, Any], outcome: dict[str, Any]) -> None:
        kind = event.get("t")
        if job_id in self.cancelling:
            return
        if kind == "stage":
            self._update(job_id, stage=event["stage"], progress=0.0, speed=None, eta=None)
        elif kind == "progress":
            self._update(
                job_id,
                stage=event.get("stage", "downloading"),
                progress=float(event.get("progress") or 0),
                speed=event.get("speed"),
                eta=event.get("eta"),
                item_index=event.get("item_index"),
                item_count=event.get("item_count"),
            )
        elif kind == "done":
            outcome["files"] = event.get("files") or []
        elif kind == "error":
            outcome.update(code=event.get("code"), raw=event.get("raw"))

    # ---- user actions ---------------------------------------------------------------------
    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(job_id)
        if job is None:
            return None
        if job["status"] == "queued":
            return self._update(
                job_id, status="cancelled", stage="cancelled", finished_at=time.time()
            )
        if job["status"] == "running" and job_id in self.procs:
            self.cancelling.add(job_id)
            self._update(job_id, stage="cancelling")
            self._signal(job_id, signal.SIGTERM)
            if self._event_loop is not None:
                self._on_loop(
                    self._event_loop.call_later,
                    CANCEL_GRACE_SECONDS,
                    self._signal,
                    job_id,
                    signal.SIGKILL,
                )
        return self.store.get(job_id)

    def retry(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(job_id)
        if job is None or job["status"] not in ("failed", "cancelled"):
            return job
        # Same id, same scratch directory: yt-dlp continues any .part files it finds there.
        updated = self._update(
            job_id,
            status="queued",
            stage="queued",
            progress=0.0,
            error_code=None,
            error_raw=None,
            finished_at=None,
        )
        self.wake()
        return updated

    def remove(self, job_id: str) -> bool:
        job = self.store.get(job_id)
        if job is None or job["status"] == "running":
            return False
        self.store.delete(job_id)
        self._remove_scratch(job)
        self.publish({"type": "removed", "id": job_id})
        return True

    def _remove_scratch(self, job: dict[str, Any]) -> None:
        """Delete the job's own scratch directory -- never the downloaded media."""
        request = job.get("request") or {}
        work = Path(request.get("work_dir") or "")
        root = Path(request.get("download_dir") or "") / ".vd-work"
        if work.name == job["id"] and work.resolve().parent == root.resolve() and work.exists():
            shutil.rmtree(work, ignore_errors=True)

    def _signal(self, job_id: str, sig: signal.Signals) -> None:
        proc = self.procs.get(job_id)
        if proc is not None:
            self._signal_proc(proc, sig)

    @staticmethod
    def _signal_proc(proc: asyncio.subprocess.Process, sig: signal.Signals) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, sig)

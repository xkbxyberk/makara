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
import logging
import os
import shutil
import signal
import sys
import time
import traceback
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import accel, paths
from app.db import JobStore
from app.settings import Settings

log = logging.getLogger("videodownloader.jobs")
CANCEL_GRACE_SECONDS = 5
WORKERS = {"download": "app.workers.download_worker", "studio": "app.workers.studio_worker"}
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
    # Said, not hidden: this download used Berk's account (where and how stays private).
    out["used_session"] = bool(request.get("cookies_from_browser"))
    return out


class JobManager:
    def __init__(
        self,
        store: JobStore,
        get_settings: Callable[[], Settings],
        on_done: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store
        self.get_settings = get_settings
        self.on_done = on_done
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        # Jobs from "picked" to "process exited" -- includes the window before a process exists.
        self.active: set[str] = set()
        self.cancelling: set[str] = set()
        # Stopped by a pause: ends "paused" (scratch kept, resumable), not "cancelled".
        self.pausing: set[str] = set()
        self._kill_timers: dict[str, asyncio.TimerHandle] = {}
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

    def announce_shutdown(self) -> None:
        """Called from the signal handler: end every event stream so the server can stop."""
        if self._event_loop is not None:
            self._event_loop.call_soon_threadsafe(self._publish_now, {"type": "shutdown"})

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
            # `active`, not `procs`: a worker only appears in `procs` once its process has
            # spawned, and several wake-ups can land in that window.
            free = self.get_settings().concurrency - len(self.active)
            if free <= 0:
                continue
            for job in self.store.next_queued(free):
                # Claim it *before* the task starts, so it can be neither picked twice nor
                # miscounted.
                self.active.add(job["id"])
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
        try:
            await self._run_worker(job)
        except asyncio.CancelledError:
            raise  # server shutdown: the row stays "running" and is requeued on the next start
        except Exception:
            # Nothing may leave a job stuck in "running" where it can be neither cancelled,
            # retried nor removed.
            proc = self.procs.get(job_id)
            if proc is not None:
                self._signal_proc(proc, signal.SIGKILL)
            self._update(
                job_id,
                status="failed",
                stage="failed",
                speed=None,
                eta=None,
                error_code="WORKER_CRASHED",
                error_raw=traceback.format_exc()[-8000:],
                finished_at=time.time(),
            )
        finally:
            self.active.discard(job_id)
            self.procs.pop(job_id, None)
            self.cancelling.discard(job_id)
            self.pausing.discard(job_id)
            timer = self._kill_timers.pop(job_id, None)
            if timer is not None:
                timer.cancel()
            self.wake()

    async def _run_worker(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        if job_id in self.cancelling:  # cancelled while it was being picked
            self._finish_cancelled(job_id)
            return
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
                WORKERS.get(job["kind"], "app.workers.download_worker"),
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
            return
        self.procs[job_id] = proc
        if job_id in self.cancelling:  # a cancel arrived while the process was spawning
            self._terminate(job_id, proc)
        assert proc.stdin and proc.stdout and proc.stderr
        request = dict(job["request"])
        settings = self.get_settings()
        if not settings.safari_login:
            # Queued (or retried) while the session was allowed, run after it was turned off.
            request["cookies_from_browser"] = None
        # Connections and the speed cap as they are now: a resume picks up a changed setting.
        request["network"] = accel.network(settings)
        proc.stdin.write(json.dumps(request).encode())
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
                    event = None
                if not isinstance(event, dict):
                    stderr_tail.append(raw.decode(errors="replace").rstrip())
                    continue
                self._apply(job_id, event, outcome)
            await proc.wait()
            await stderr_task
        finally:
            if proc.returncode is None:
                self._signal_proc(proc, signal.SIGKILL)

        # A finished job is finished, even if a cancel raced its last moments.
        if "files" in outcome:
            self._update(
                job_id,
                status="done",
                stage="done",
                progress=1.0,
                speed=None,
                eta=None,
                output_files=outcome["files"],
                warnings=outcome.get("warnings") or [],
                finished_at=time.time(),
            )
            if self.on_done is not None:
                try:
                    self.on_done(job, outcome)
                except Exception as exc:  # the file is safely on disk either way
                    log.exception("cataloguing job %s failed", job_id)
                    self.publish({"type": "library_error", "id": job_id, "raw": str(exc)})
        elif job_id in self.cancelling:
            self._finish_cancelled(job_id)
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

    def _finish_cancelled(self, job_id: str) -> None:
        paused = job_id in self.pausing
        self._update(
            job_id,
            status="paused" if paused else "cancelled",
            stage="paused" if paused else "cancelled",
            speed=None,
            eta=None,
            finished_at=time.time(),
        )

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
            outcome["outputs"] = event.get("outputs") or []
            outcome["meta"] = event.get("meta") or {}
            outcome["warnings"] = event.get("warnings") or []
            outcome["separate"] = bool(event.get("separate"))
        elif kind == "error":
            outcome.update(code=event.get("code"), raw=event.get("raw"))

    # ---- user actions ---------------------------------------------------------------------
    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(job_id)
        if job is None:
            return None
        if job["status"] in ("queued", "paused"):
            return self._update(
                job_id, status="cancelled", stage="cancelled", finished_at=time.time()
            )
        if job["stage"] == "finalizing":
            # The finished files are being moved into place; stopping now would leave them
            # there with no catalogue record. Let it complete.
            return job
        if job["status"] == "running" and job_id not in self.cancelling:
            self.cancelling.add(job_id)
            self._update(job_id, stage="cancelling")
            proc = self.procs.get(job_id)
            if proc is not None:
                self._terminate(job_id, proc)
            # No process yet: _run_worker acts on the flag the moment the process exists.
        return self.store.get(job_id)

    def pause(self, job_id: str) -> dict[str, Any] | None:
        """Stop a download but keep its scratch directory, so a resume continues the `.part`
        files (and aria2c's control files) instead of starting over."""
        job = self.store.get(job_id)
        if job is None:
            return None
        if job.get("kind") == "studio":
            return job  # an FFmpeg run cannot continue where it stopped; cancel it instead
        if job["status"] == "queued":
            return self._update(job_id, status="paused", stage="paused")
        if job["status"] == "running" and job_id not in self.cancelling:
            if job["stage"] == "finalizing":
                return job  # as cancel: the files are being moved into place
            self.pausing.add(job_id)
            self.cancel(job_id)
            return self._update(job_id, stage="pausing")
        return job

    def resume(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(job_id)
        if job is None or job["status"] != "paused":
            return job
        updated = self._update(job_id, status="queued", stage="queued", speed=None, eta=None)
        self.wake()
        return updated

    def pause_all(self) -> int:
        jobs = [
            j
            for j in self.store.all()
            if j["status"] in ("queued", "running") and j.get("kind") != "studio"
        ]
        for job in jobs:
            self.pause(job["id"])
        return len(jobs)

    def resume_all(self) -> int:
        jobs = [j for j in self.store.all() if j["status"] == "paused"]
        # Oldest first, so they go back in the order they were queued.
        for job in sorted(jobs, key=lambda j: j.get("created_at") or 0):
            self.resume(job["id"])
        return len(jobs)

    def _terminate(self, job_id: str, proc: asyncio.subprocess.Process) -> None:
        self._signal_proc(proc, signal.SIGTERM)
        self._on_loop(self._arm_kill_timer, job_id, proc)

    def _arm_kill_timer(self, job_id: str, proc: asyncio.subprocess.Process) -> None:
        if self._event_loop is None:
            return
        # Bound to *this* process object, and cancelled when it exits: a retry started within
        # the grace period runs in a new process that this timer must never touch.
        self._kill_timers[job_id] = self._event_loop.call_later(
            CANCEL_GRACE_SECONDS, self._kill_if_alive, proc
        )

    def _kill_if_alive(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is None:
            self._signal_proc(proc, signal.SIGKILL)

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
        root = Path(
            request.get("scratch_root") or Path(request.get("download_dir") or "") / ".vd-work"
        )
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

"""A worker never outlives the server that started it.

Workers run in sessions of their own (so a cancel can kill the whole group: yt-dlp, FFmpeg,
deno). That also means a signal to the server's group never reaches them, and if the server is
killed outright (SIGKILL, a crash) nobody stops them: they would keep writing `.part` files that
the requeued job, on the next start, writes too. So each worker watches its parent and, once
re-parented, kills its own group.
"""

from __future__ import annotations

import os
import signal
import threading
import time

CHECK_SECONDS = 0.5


def hold() -> None:
    parent = os.getppid()

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(CHECK_SECONDS)
        if os.getpgrp() == os.getpid():
            os.killpg(0, signal.SIGKILL)  # this worker's own group: it and everything it started
        else:
            os.kill(os.getpid(), signal.SIGKILL)  # run by hand: never take a shell's group down

    threading.Thread(target=watch, name="lifeline", daemon=True).start()

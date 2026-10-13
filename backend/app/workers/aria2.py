"""aria2c inside a download worker, with its progress.

yt-dlp runs aria2c without reporting progress, and lets it write to the worker's stdout --
which carries this worker's JSON protocol. `install()` makes yt-dlp's aria2c downloader pipe
aria2c's output instead: its summary lines (`[#2089b0 4.0MiB/10MiB(40%) CN:16 DL:2.0MiB
ETA:3s]`, asked for once a second) become ordinary yt-dlp progress hooks, and the other lines
are kept as its error text. Only this worker process is patched.
"""

from __future__ import annotations

import re
import subprocess
from collections import deque
from pathlib import Path
from typing import Any

READOUT = re.compile(
    r"\[#\w+ (?P<done>[\d.]+)(?P<done_unit>[KMGT]?i?B)/(?P<total>[\d.]+)(?P<total_unit>[KMGT]?i?B)"
    r"\((?P<percent>\d+)%\)(?P<rest>[^\]]*)\]"
)
SPEED = re.compile(r"DL:(?P<value>[\d.]+)(?P<unit>[KMGT]?i?B)")
ETA = re.compile(r"ETA:(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?")
UNITS = {"B": 1, "KiB": 1 << 10, "MiB": 1 << 20, "GiB": 1 << 30, "TiB": 1 << 40}
# The frame around each summary; not worth keeping as error text.
CHROME = re.compile(r"^\s*(\*\*\*|=+$|-+$|FILE:|\[#)")


def _bytes(value: str, unit: str) -> int:
    return int(float(value) * UNITS.get(unit, 1))


def parse(line: str) -> dict[str, Any] | None:
    """One readout line -> downloaded/total bytes, speed (bytes/s) and ETA (s), or None."""
    match = READOUT.search(line)
    if not match:
        return None
    total = _bytes(match["total"], match["total_unit"])
    # The byte counts are rounded to one decimal; never report more than the total.
    done = min(_bytes(match["done"], match["done_unit"]), total) if total else 0
    speed = SPEED.search(match["rest"])
    eta = ETA.search(match["rest"])
    seconds = None
    if eta and any(eta.groups()):
        seconds = int(eta["h"] or 0) * 3600 + int(eta["m"] or 0) * 60 + int(eta["s"] or 0)
    return {
        "downloaded_bytes": done,
        "total_bytes": total or None,
        "speed": _bytes(speed["value"], speed["unit"]) if speed else None,
        "eta": seconds,
    }


def _output_name(cmd: list[str]) -> str:
    """The `--out` file aria2c writes (yt-dlp prefixes it with "./")."""
    name = cmd[cmd.index("--out") + 1] if "--out" in cmd else ""
    return Path(name).name


def _call_process(self: Any, cmd: list[str], info_dict: dict[str, Any]) -> tuple[str, str, int]:
    tmpname = _output_name(cmd)
    filename = tmpname.removesuffix(".part")
    # Once a second, after yt-dlp's own `--summary-interval=0` (the last one counts).
    cmd = [
        *cmd[: cmd.index("--")],
        "--summary-interval=1",
        "--enable-color=false",
        *cmd[cmd.index("--") :],
    ]
    tail: deque[str] = deque(maxlen=40)
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    ) as proc:
        assert proc.stdout
        for line in proc.stdout:
            progress = parse(line)
            if progress is not None:
                self._hook_progress(
                    {
                        "status": "downloading",
                        "filename": filename,
                        "tmpfilename": tmpname,
                        **progress,
                    },
                    info_dict,
                )
            elif line.strip() and not CHROME.match(line):
                tail.append(line.rstrip())
    return "", "\n".join(tail), proc.returncode


def install() -> None:
    from yt_dlp.downloader.external import Aria2cFD

    Aria2cFD._call_process = _call_process

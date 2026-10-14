"""aria2c inside a download worker, with its progress.

yt-dlp runs aria2c without reporting progress, and lets it write to the worker's stdout --
which carries this worker's JSON protocol. `install()` makes yt-dlp's aria2c downloader pipe
aria2c's output instead: its summary lines (`[#2089b0 4.0MiB/10MiB(40%) CN:16 DL:2.0MiB
ETA:3s]`, asked for once a second) become ordinary yt-dlp progress hooks, and the other lines
are kept as its error text. Only this worker process is patched.
"""

from __future__ import annotations

import re
import struct
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
CONNECTIONS = re.compile(r"CN:(?P<n>\d+)")
CELLS = 48  # the segment map's resolution in İndirmeler
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


def pieces(control: Path, cells: int = CELLS) -> str | None:
    """Which parts of the file are on disk, from aria2c's own control file (`<file>.aria2`,
    saved every second): one digit per cell, 0 (nothing) to 9 (complete). Format: version,
    extension, info hash, piece length, total length, upload length, the finished pieces'
    bitfield, then each in-flight piece with its 16 KiB blocks' bitfield
    (aria2's "Control File (*.aria2) Format"; version 1 is big-endian)."""
    try:
        data = control.read_bytes()
        version, _ext, hash_len = struct.unpack_from(">HII", data, 0)
        if version != 1:
            return None
        at = 10 + hash_len
        piece_len, total, _uploaded, field_len = struct.unpack_from(">IQQI", data, at)
        at += 24
        field = data[at : at + field_len]
        at += field_len
        count = -(-total // piece_len) if piece_len else 0
        done = [float(field[i // 8] >> (7 - i % 8) & 1) for i in range(count)]
        (inflight,) = struct.unpack_from(">I", data, at)
        at += 4
        for _ in range(inflight):
            index, _length, blocks_len = struct.unpack_from(">III", data, at)
            at += 12
            blocks = data[at : at + blocks_len]
            at += blocks_len
            bits = sum(bin(b).count("1") for b in blocks)
            if 0 <= index < count and blocks_len:
                done[index] = max(done[index], bits / (blocks_len * 8))
    except (OSError, struct.error, IndexError):
        return None
    if not done:
        return None
    out = []
    for c in range(cells):
        part = done[
            c * len(done) // cells : max((c + 1) * len(done) // cells, c * len(done) // cells + 1)
        ]
        out.append(str(min(9, int(sum(part) / len(part) * 9))))
    return "".join(out)


def _output_name(cmd: list[str]) -> str:
    """The `--out` file aria2c writes (yt-dlp prefixes it with "./")."""
    name = cmd[cmd.index("--out") + 1] if "--out" in cmd else ""
    return Path(name).name


def _call_process(self: Any, cmd: list[str], info_dict: dict[str, Any]) -> tuple[str, str, int]:
    tmpname = _output_name(cmd)
    filename = tmpname.removesuffix(".part")
    folder = cmd[cmd.index("--dir") + 1] if "--dir" in cmd else "."
    control = Path(folder) / f"{tmpname}.aria2"
    # Once a second, after yt-dlp's own `--summary-interval=0` (the last one counts).
    cmd = [
        *cmd[: cmd.index("--")],
        "--summary-interval=1",
        "--enable-color=false",
        "--auto-save-interval=1",  # the control file is the segment map (see `pieces`)
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
                connections = CONNECTIONS.search(line)
                progress["vd_connections"] = int(connections["n"]) if connections else None
                progress["vd_pieces"] = pieces(control)
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

"""What Finder shows about a downloaded file (P6f): "Nereden" (kMDItemWhereFroms), the page
it came from, as Safari's own downloads have. An extended attribute; never the file's bytes."""

from __future__ import annotations

import ctypes
import ctypes.util
import plistlib
import sys
from pathlib import Path

WHERE_FROMS = b"com.apple.metadata:kMDItemWhereFroms"
_libc = (
    ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True) if sys.platform == "darwin" else None
)


def set_where_from(path: Path, urls: list[str]) -> bool:
    """Record the source page(s). Best effort: a volume without xattrs simply has no "Nereden"."""
    if _libc is None or not urls:
        return False
    value = plistlib.dumps([u for u in urls if u][:4], fmt=plistlib.FMT_BINARY)
    # int setxattr(const char *path, const char *name, const void *value, size_t size,
    #              u_int32_t position, int options)
    result = _libc.setxattr(str(path).encode(), WHERE_FROMS, value, len(value), 0, 0)
    return int(result) == 0


def where_from(path: Path) -> list[str]:
    """Read it back (tests, and the library someday)."""
    if _libc is None:
        return []
    size = _libc.getxattr(str(path).encode(), WHERE_FROMS, None, 0, 0, 0)
    if size <= 0:
        return []
    buffer = ctypes.create_string_buffer(size)
    if _libc.getxattr(str(path).encode(), WHERE_FROMS, buffer, size, 0, 0) != size:
        return []
    value = plistlib.loads(buffer.raw)
    return [str(v) for v in value] if isinstance(value, list) else []

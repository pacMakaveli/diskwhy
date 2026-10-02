"""Sizing helpers.

All of them shell out to du and find.
That is far faster than walking the tree in Python and counts hard links the way the OS does.

"""

from __future__ import annotations

import os
import stat
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# --- Cache ---

CACHE_TTL = 300  # seconds a computed result is reused
_cache: dict = {}
_lock = threading.Lock()


def cached(key, compute):
    """Return a cached value, computing and storing it when missing or expired.

    Args:
        key: Hashable cache key.
        compute: Zero-argument callable that produces the value.

    Returns:
        The cached or freshly computed value.

    """
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    value = compute()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def clear_cache() -> None:
    """Drop every cached result, for example after something was removed."""
    with _lock:
        _cache.clear()


# --- Sizing ---


def _run(cmd: list[str], timeout: int) -> str:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        ).stdout
    except subprocess.TimeoutExpired:
        return ""


def size_of(path: str, timeout: int = 180) -> int | None:
    """Measure the disk usage of one path.

    Args:
        path: File or directory to measure.
        timeout: Seconds before du is abandoned.

    Returns:
        The size in bytes, or None when the path is missing or unreadable.

    """

    def compute():
        if not os.path.lexists(path):
            return None
        first = _run(["du", "-sk", "-x", path], timeout).split("\t", 1)[0]
        return int(first) * 1024 if first.isdigit() else None

    return cached(("size", path), compute)


def sizes_of(paths: list[str], workers: int = 6) -> dict[str, int | None]:
    """Measure several paths in parallel.

    Args:
        paths: Paths to measure.
        workers: Number of du processes to run at once.

    Returns:
        A mapping of each path to its size in bytes, or None where unreadable.

    """
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(paths, pool.map(size_of, paths)))


def children(path: str, timeout: int = 180) -> dict:
    """List the immediate children of a directory with their sizes.

    Directories are sized by du and plain files straight from lstat.
    macOS du cannot combine -a with -d, and -d1 on its own lists directories only.

    Args:
        path: Directory to list.
        timeout: Seconds before du is abandoned.

    Returns:
        A dict with `path`, `total` (bytes or None) and `entries`, largest first.
        Each entry has `name`, `path`, `size`, `is_dir` and `is_link`.

    """

    def compute():
        out = _run(["du", "-k", "-d1", "-x", path], timeout)
        base = path.rstrip("/") or "/"
        total, rows = None, []
        for line in out.splitlines():
            kb, _, entry = line.partition("\t")
            if not kb.isdigit():
                continue
            if entry.rstrip("/") == base:
                total = int(kb) * 1024
                continue
            rows.append(
                {
                    "name": os.path.basename(entry),
                    "path": entry,
                    "size": int(kb) * 1024,
                    "is_dir": True,
                    "is_link": False,
                }
            )

        seen = {r["name"] for r in rows}
        try:
            for e in os.scandir(path):
                if e.name in seen:
                    continue
                st = e.stat(follow_symlinks=False)
                rows.append(
                    {
                        "name": e.name,
                        "path": e.path,
                        "size": st.st_blocks * 512,
                        "is_dir": stat.S_ISDIR(st.st_mode),
                        "is_link": stat.S_ISLNK(st.st_mode),
                    }
                )
        except OSError:
            pass

        rows.sort(key=lambda r: r["size"], reverse=True)
        return {"path": path, "total": total, "entries": rows}

    return cached(("children", path), compute)


# --- Searching ---


def large_files(
    root: str, min_mb: int = 200, limit: int = 100, timeout: int = 180
) -> list[dict]:
    """Find the largest files under a directory.

    Args:
        root: Directory to search, without crossing filesystems.
        min_mb: Smallest file size to report, in megabytes.
        limit: Maximum number of files to return.
        timeout: Seconds before find is abandoned.

    Returns:
        Dicts with `path`, `size` (bytes on disk) and `mtime`, largest first.

    """

    def compute():
        out = _run(
            ["find", root, "-xdev", "-type", "f", "-size", f"+{min_mb}M", "-print0"],
            timeout,
        )
        rows = []
        for entry in filter(None, out.split("\0")):
            try:
                st = os.lstat(entry)
            except OSError:
                continue
            rows.append(
                {"path": entry, "size": st.st_blocks * 512, "mtime": int(st.st_mtime)}
            )
        rows.sort(key=lambda r: r["size"], reverse=True)
        return rows[:limit]

    return cached(("large", root, min_mb, limit), compute)


def find_dirs(
    root: str, name: str, max_depth: int = 6, timeout: int = 120
) -> list[str]:
    """Find directories with a given name without descending into them.

    Args:
        root: Directory to search.
        name: Exact directory name to match, for example `node_modules`.
        max_depth: How many levels below root to look.
        timeout: Seconds before find is abandoned.

    Returns:
        The matching directory paths.

    """
    out = _run(
        [
            "find",
            root,
            "-maxdepth",
            str(max_depth),
            "-name",
            name,
            "-type",
            "d",
            "-prune",
            "-print0",
        ],
        timeout,
    )
    return [p for p in out.split("\0") if p]

"""Guards for the one destructive operation diskwhy has: removing a path.

Everything here answers a single question, "may this path be removed?".
It has no side effects, so it can be tested without touching a disk.

"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# --- Policy ---

HOME = os.path.realpath(os.path.expanduser("~"))  # the user's home, symlinks resolved

ALLOWED_ROOTS = [
    HOME,
    "/opt/homebrew",
    "/usr/local",
]  # removal is only offered inside these

# Directories that may be emptied item by item but never removed themselves.
PROTECTED_EXACT = {
    HOME,
    f"{HOME}/Library",
    f"{HOME}/Documents",
    f"{HOME}/Desktop",
    f"{HOME}/Downloads",
    f"{HOME}/Projects",
    f"{HOME}/Library/Application Support",
    f"{HOME}/Library/Caches",
    f"{HOME}/Library/Containers",
    f"{HOME}/Library/Mobile Documents",
    "/opt/homebrew",
    "/opt/homebrew/bin",
    "/opt/homebrew/opt",
    "/opt/homebrew/var",
    "/opt/homebrew/Cellar",
    "/opt/homebrew/lib",
    "/opt/homebrew/etc",
    "/opt/homebrew/share",
    "/opt/homebrew/include",
    "/usr/local",
}

# Credentials and keys: neither the directory nor anything under it.
PROTECTED_TREES = [
    f"{HOME}/.ssh",
    f"{HOME}/.gnupg",
    f"{HOME}/.aws",
    f"{HOME}/.kube",
    f"{HOME}/Library/Keychains",
]


# --- Path helpers ---


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def resolve(path: str) -> str:
    """Resolve parent symlinks of a path but keep its final component as given.

    Removing a symlink must remove the link, never what it points at.

    Args:
        path: An absolute path, or one starting with `~`.

    Returns:
        The absolute path with every parent resolved and the last component untouched.

    """
    path = os.path.abspath(os.path.expanduser(path))
    return os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))


# --- Running database detection ---


def _process_commands() -> list[str]:
    try:
        out = subprocess.run(
            ["ps", "-axo", "command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return []
    return out.splitlines()


def is_active_db_dir(path: str, commands: list[str] | None = None) -> bool:
    """Tell whether a running postgres or mysqld was started against a data directory.

    This matches on the server's own `--datadir` or `-D` argument rather than on a pid file.
    A copied backup carries a stale pid file that a recycled pid can make look alive.

    Args:
        path: The candidate data directory.
        commands: Process command lines to search, read from `ps` when omitted.

    Returns:
        True when some process was started with this directory as its data directory.

    """
    commands = _process_commands() if commands is None else commands
    pattern = re.compile(
        r"(--datadir=|\s-D\s+)" + re.escape(path.rstrip("/")) + r"/?(\s|$)"
    )
    return any(pattern.search(cmd) for cmd in commands)


def holds_db(path: str) -> bool:
    """Tell whether a directory looks like a Postgres or MySQL data directory.

    Args:
        path: The directory to inspect.

    Returns:
        True when it contains `PG_VERSION` (Postgres) or `mysql.ibd` (MySQL).

    """
    return os.path.exists(os.path.join(path, "PG_VERSION")) or os.path.exists(
        os.path.join(path, "mysql.ibd")
    )


# --- The removal decision ---


def removal_blocker(path: str, commands: list[str] | None = None) -> str | None:
    """Explain why a path must not be removed.

    Args:
        path: The path the user wants to remove.
        commands: Process command lines for the running-database check, read from `ps` when omitted.

    Returns:
        A human-readable reason, or None when removal is allowed.

    """
    if not os.path.isabs(os.path.expanduser(path)):
        return "path must be absolute"

    target = resolve(path)

    if not os.path.lexists(target):
        return "path does not exist"
    if not any(_under(target, root) for root in ALLOWED_ROOTS):
        return "outside the directories diskwhy is allowed to remove from"
    if target in PROTECTED_EXACT:
        return "protected directory, remove its contents instead"
    if any(_under(target, tree) for tree in PROTECTED_TREES):
        return "credentials and keys are never removable from here"

    # Never delete a directory that is, or contains, a live database cluster.
    if os.path.isdir(target) and not os.path.islink(target):
        commands = _process_commands() if commands is None else commands
        candidates = [target]
        try:
            candidates += [
                e.path for e in os.scandir(target) if e.is_dir(follow_symlinks=False)
            ]
        except OSError:
            pass
        for candidate in candidates:
            if holds_db(candidate) and is_active_db_dir(candidate, commands):
                return f"{Path(candidate).name} is the data directory of a running database"

    return None

"""Places on a developer Mac that routinely hold gigabytes, with a verdict on how safe each is to clear.

Every spot has a `kind`:

- `regenerable`: the owning tool rebuilds it on demand.
- `review`: probably fine to clear, but it is your call.
- `data`: holds real state, so look before you remove it.
- `stale`: a database data directory that no running server uses.

"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass

from . import safety, scanner

HOME = safety.HOME  # home directory that the static spots are rooted in


@dataclass
class Spot:
    """A known location that can hold a lot of disk space.

    Args:
        id: Stable identifier used by the UI.
        label: Short display name.
        path: Absolute path on disk.
        kind: One of `regenerable`, `review`, `data` or `stale`.
        note: Why it is safe or unsafe to clear.
        hint: A cleanup command the owning tool offers, shown but never run.

    """

    id: str
    label: str
    path: str
    kind: str
    note: str = ""
    hint: str = ""


def _h(*parts: str) -> str:
    return os.path.join(HOME, *parts)


# --- Known locations ---

STATIC_SPOTS = [
    Spot("trash", "Trash", _h(".Trash"), "regenerable", "Already deleted; space is only freed once it is emptied."),
    Spot("derived", "Xcode DerivedData", _h("Library/Developer/Xcode/DerivedData"), "regenerable", "Build products Xcode recreates."),
    Spot("devsupport", "Xcode iOS DeviceSupport", _h("Library/Developer/Xcode/iOS DeviceSupport"), "regenerable", "Symbols re-downloaded when a device is plugged in."),
    Spot("simulators", "iOS Simulators", _h("Library/Developer/CoreSimulator/Devices"), "review", "Simulator disk images and app data.", "xcrun simctl delete unavailable"),
    Spot("lib-caches", "~/Library/Caches", _h("Library/Caches"), "regenerable", "App caches; apps rebuild what they need."),
    Spot("logs", "~/Library/Logs", _h("Library/Logs"), "regenerable", "Diagnostic logs."),
    Spot("npm", "npm cache", _h(".npm"), "regenerable", "", "npm cache clean --force"),
    Spot("pnpm", "pnpm store", _h("Library/pnpm"), "regenerable", "", "pnpm store prune"),
    Spot("yarn", "Yarn cache", _h(".yarn"), "regenerable", "", "yarn cache clean"),
    Spot("dot-cache", "~/.cache", _h(".cache"), "review", "Includes ML model downloads (e.g. Hugging Face) that are slow to re-fetch."),
    Spot("pip", "pip cache", _h("Library/Caches/pip"), "regenerable", "", "pip cache purge"),
    Spot("playwright", "Playwright browsers", _h("Library/Caches/ms-playwright"), "regenerable", "", "npx playwright install"),
    Spot("brew-cache", "Homebrew download cache", _h("Library/Caches/Homebrew"), "regenerable", "", "brew cleanup -s"),
    Spot("brew-cellar", "Homebrew Cellar", "/opt/homebrew/Cellar", "review", "Look for old versions (several llvm, postgres, mysql).", "brew autoremove && brew cleanup"),
    Spot("chrome-ai", "Chrome on-device AI model", _h("Library/Application Support/Google/Chrome/OptGuideOnDeviceModel"), "regenerable", "Chrome re-downloads it."),
    Spot("google-updater", "Google updater cache", _h("Library/Application Support/Google/GoogleUpdater"), "regenerable", ""),
    Spot("cursor-updater", "Cursor updater cache", _h("Library/Caches/com.todesktop.230313mzl4w4u92.ShipIt"), "regenerable", ""),
    Spot("docker", "Docker Desktop data", _h("Library/Containers/com.docker.docker"), "data", "Images, volumes and containers.", "docker system prune"),
    Spot("downloads", "Downloads", _h("Downloads"), "review", "Yours to judge."),
    Spot("icloud", "iCloud Drive", _h("Library/Mobile Documents"), "data", "Removing items here removes them from iCloud too."),
]  # fmt: skip


# --- Detected locations ---


def _newest_mtime(path: str) -> float:
    try:
        return max(os.lstat(e.path).st_mtime for e in os.scandir(path))
    except OSError, ValueError:
        return os.lstat(path).st_mtime


def database_spots(var_dir: str = "/opt/homebrew/var") -> list[Spot]:
    """Detect Postgres and MySQL data directories and whether a server uses them.

    Args:
        var_dir: Directory whose children are searched, Homebrew's `var` by default.

    Returns:
        One spot per data directory: `data` when a server is running against it, `stale` otherwise.

    """
    if not os.path.isdir(var_dir):
        return []
    commands = safety._process_commands()
    spots = []
    for entry in sorted(os.scandir(var_dir), key=lambda e: e.name):
        if not entry.is_dir(follow_symlinks=False) or not safety.holds_db(entry.path):
            continue
        engine = (
            "Postgres"
            if os.path.exists(os.path.join(entry.path, "PG_VERSION"))
            else "MySQL"
        )
        active = safety.is_active_db_dir(entry.path, commands)
        days = int((time.time() - _newest_mtime(entry.path)) / 86400)
        state = (
            "In use by a running server" if active else "No running server uses this"
        )
        spots.append(
            Spot(
                f"db-{entry.name}",
                f"{engine} data: {entry.name}",
                entry.path,
                "data" if active else "stale",
                f"{state} · last written {days}d ago",
            )
        )
    return spots


def node_modules_spots(roots: list[str], top: int = 15) -> list[Spot]:
    """Find the largest node_modules directories under some project roots.

    Args:
        roots: Folders to search.
        top: How many of the largest to keep.

    Returns:
        Up to `top` regenerable spots, largest first.

    """
    found = [p for root in roots for p in scanner.find_dirs(root, "node_modules")]
    sizes = scanner.sizes_of(found)
    biggest = sorted(found, key=lambda p: sizes.get(p) or 0, reverse=True)[:top]
    return [
        Spot(
            f"nm-{i}",
            f"node_modules: {os.path.relpath(p, HOME)}",
            p,
            "regenerable",
            "",
            "npm install / pnpm install",
        )
        for i, p in enumerate(biggest)
    ]


# --- Assembly ---


def collect(project_roots: list[str]) -> list[dict]:
    """Gather every known and detected spot, sized and checked for removability.

    Args:
        project_roots: Folders to search for node_modules.

    Returns:
        Dicts with the spot fields plus `size`, `removable` and `blocker`, largest first.
        Spots that do not exist or measure zero are left out.

    """
    spots = [s for s in STATIC_SPOTS if os.path.lexists(s.path)]
    spots += database_spots()
    spots += node_modules_spots(project_roots)

    sizes = scanner.sizes_of([s.path for s in spots])
    commands = safety._process_commands()
    rows = []
    for spot in spots:
        size = sizes.get(spot.path)
        if not size:
            continue
        blocker = safety.removal_blocker(spot.path, commands)
        rows.append(
            {
                **asdict(spot),
                "size": size,
                "removable": blocker is None,
                "blocker": blocker,
            }
        )
    rows.sort(key=lambda r: r["size"], reverse=True)
    return rows

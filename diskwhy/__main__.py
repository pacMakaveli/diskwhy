"""Command line entry point: `python3 -m diskwhy` or the installed `diskwhy` command."""

from __future__ import annotations

import argparse
import os

from .server import serve


def main() -> None:
    """Parse the command line and start the dashboard."""
    parser = argparse.ArgumentParser(
        prog="diskwhy", description="See what is eating your disk, and clear it safely."
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="port to listen on (default 8765)"
    )
    parser.add_argument(
        "--projects",
        action="append",
        default=[],
        help="folder to scan for node_modules (repeatable, default ~/Projects)",
    )
    parser.add_argument(
        "--no-open", action="store_true", help="don't open a browser tab"
    )
    args = parser.parse_args()

    roots = [os.path.expanduser(p) for p in args.projects] or [
        os.path.expanduser("~/Projects")
    ]
    serve(
        args.port, [r for r in roots if os.path.isdir(r)], open_browser=not args.no_open
    )


if __name__ == "__main__":
    main()

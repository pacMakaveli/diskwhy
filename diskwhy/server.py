"""Localhost-only HTTP server.

It reads the disk freely.
The single write operation, remove, always goes through `safety.removal_blocker` first.

"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import hotspots, safety, scanner

# --- Constants ---

STATIC = Path(__file__).parent / "static"  # directory holding index.html
VOLUME = (
    "/System/Volumes/Data" if os.path.isdir("/System/Volumes/Data") else "/"
)  # volume whose free space is shown


class RemoveError(Exception):
    """Raised when a removal is refused or fails part way."""


# --- Removal ---


def trash_path(target: str) -> None:
    """Move a path into the user's Trash, never overwriting what is already there.

    Args:
        target: Absolute path to move.

    """
    trash = os.path.join(safety.HOME, ".Trash")
    os.makedirs(trash, exist_ok=True)
    name, dest, n = os.path.basename(target), None, 0
    while dest is None or os.path.lexists(dest):
        dest = os.path.join(trash, name if n == 0 else f"{name} {n}")
        n += 1
    shutil.move(target, dest)


def delete_path(target: str) -> None:
    """Delete a path permanently, removing a symlink as the link and not its target.

    Args:
        target: Absolute path to delete.

    Raises:
        RemoveError: When some items inside a directory could not be removed.

    """
    if os.path.islink(target) or not os.path.isdir(target):
        os.unlink(target)
        return
    failures = []
    shutil.rmtree(target, onexc=lambda fn, p, exc: failures.append(f"{p}: {exc}"))
    if failures:
        raise RemoveError(
            f"{len(failures)} item(s) could not be removed, e.g. {failures[0]}"
        )


def remove(path: str, mode: str, confirm: str) -> dict:
    """Remove a path after every safety check has passed.

    Args:
        path: The path to remove.
        mode: `trash` to move it to the Trash, `delete` to remove it permanently.
        confirm: For `delete`, the item's exact name, typed by the user.

    Returns:
        A dict with the removed `removed` path, the `mode` used and the `size` freed in bytes.

    Raises:
        RemoveError: When the path is protected, the confirmation is wrong or the mode is unknown.

    """
    blocker = safety.removal_blocker(path)
    if blocker:
        raise RemoveError(blocker)

    target = safety.resolve(path)
    if mode == "delete" and confirm != os.path.basename(target):
        raise RemoveError("type the item's exact name to confirm permanent deletion")
    if mode not in ("trash", "delete"):
        raise RemoveError("mode must be 'trash' or 'delete'")

    size = scanner.size_of(target) or 0
    (trash_path if mode == "trash" else delete_path)(target)
    scanner.clear_cache()
    return {"removed": target, "mode": mode, "size": size}


# --- HTTP ---


def make_handler(token: str, port: int, project_roots: list[str]):
    """Build the request handler class bound to one token, port and set of project roots.

    Args:
        token: Secret every request must present.
        port: Port the server listens on, used to validate the Host header.
        project_roots: Folders searched for node_modules.

    Returns:
        A `BaseHTTPRequestHandler` subclass.

    """
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        """Serves the dashboard page and its JSON API."""

        server_version = "diskwhy"

        def log_message(self, *_):
            """Silence per-request logging."""

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _host_ok(self) -> bool:
            if self.headers.get("Host") in allowed_hosts:
                return True
            self._json({"error": "bad host"}, 403)
            return False

        def _token_ok(self, supplied: str | None) -> bool:
            if supplied and hmac.compare_digest(supplied, token):
                return True
            self._json({"error": "bad token"}, 403)
            return False

        def do_GET(self):
            """Serve the page (token in the URL) and the read-only API (token in a header)."""
            if not self._host_ok():
                return
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}

            if url.path == "/":
                if not self._token_ok(query.get("t")):
                    return
                html = (STATIC / "index.html").read_text().replace("__TOKEN__", token)
                return self._send(200, html.encode(), "text/html; charset=utf-8")

            if not self._token_ok(self.headers.get("X-DiskWhy-Token")):
                return

            try:
                if url.path == "/api/volume":
                    usage = shutil.disk_usage(VOLUME)
                    return self._json(
                        {"total": usage.total, "used": usage.used, "free": usage.free}
                    )
                if url.path == "/api/hotspots":
                    return self._json(
                        scanner.cached(
                            ("hotspots",), lambda: hotspots.collect(project_roots)
                        )
                    )
                if url.path == "/api/ls":
                    path = query.get("path", safety.HOME)
                    if not os.path.isabs(path) or not os.path.isdir(path):
                        return self._json({"error": "not a directory"}, 400)
                    result = scanner.children(path)
                    commands = safety._process_commands()
                    entries = [
                        {**e, "blocker": safety.removal_blocker(e["path"], commands)}
                        for e in result["entries"]
                    ]
                    return self._json({**result, "entries": entries})
                if url.path == "/api/large":
                    root = query.get("root", safety.HOME)
                    if not os.path.isabs(root) or not os.path.isdir(root):
                        return self._json({"error": "not a directory"}, 400)
                    return self._json(
                        scanner.large_files(root, int(query.get("min_mb", 200)))
                    )
            except (ValueError, OSError) as exc:
                return self._json({"error": str(exc)}, 400)

            self._json({"error": "not found"}, 404)

        def do_POST(self):
            """Handle `POST /api/remove`, the only write operation."""
            if not self._host_ok() or not self._token_ok(
                self.headers.get("X-DiskWhy-Token")
            ):
                return
            if urlparse(self.path).path != "/api/remove":
                return self._json({"error": "not found"}, 404)
            try:
                body = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"
                )
                self._json(
                    remove(
                        body.get("path", ""),
                        body.get("mode", ""),
                        body.get("confirm", ""),
                    )
                )
            except RemoveError as exc:
                self._json({"error": str(exc)}, 409)
            except (ValueError, OSError) as exc:
                self._json({"error": str(exc)}, 400)

    return Handler


def serve(port: int, project_roots: list[str], open_browser: bool = True) -> None:
    """Run the dashboard until interrupted.

    A fresh token is generated for every run and printed as part of the URL.

    Args:
        port: Port to listen on, bound to 127.0.0.1 only.
        project_roots: Folders searched for node_modules.
        open_browser: Whether to open the dashboard in the default browser.

    """
    token = secrets.token_urlsafe(24)
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", port), make_handler(token, port, project_roots)
    )
    url = f"http://127.0.0.1:{port}/?t={token}"
    print(f"diskwhy running at {url}\nCtrl+C to stop.")
    if open_browser:
        import webbrowser

        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

# Architecture

> How diskwhy is put together, and why.

## Overview

Developer Macs fill up quietly.
Package caches, Xcode artefacts, Homebrew versions and forgotten database data directories add up to tens of gigabytes, and none of them show up in a single place.

diskwhy is a small local web dashboard that answers "what is eating this disk?" and lets you clear it.
It runs on your own machine, reads the disk directly, and has exactly one write operation: removing a path, behind a set of guards.

It is written in Python using only the standard library, so there is nothing to install beyond the interpreter.

## Structure

```text
diskwhy/
  __main__.py     command line entry point
  server.py       HTTP server, JSON API, and the remove operation
  hotspots.py     known and detected space hogs, each with a safety verdict
  scanner.py      du/find wrappers, the result cache
  safety.py       the rules for what may be removed
  static/
    index.html    the whole UI (HTML, CSS and JS in one file, no build step)
tests/            unittest-style tests, run by pytest
docs/             this documentation
```

Requests flow one way: the browser calls `server.py`, which asks `hotspots.py` or `scanner.py` for data and `safety.py` for permission.
`safety.py` imports nothing from the rest of the package, so the rules can be tested without a disk or a server.

## Key decisions

- **Sizes come from `du`, not a Python walk.**
  It is much faster on large trees and counts hard links the way the OS does.
  The trade-off is that APFS clones can make a directory look bigger than the space you would get back.
  macOS `du` cannot combine `-a` with `-d`, and `-d1` alone lists directories only, so plain files are sized from `lstat` instead.
- **Reads are open, the one write is guarded.**
  `safety.removal_blocker` is the only path to deletion, and the server calls it again at removal time rather than trusting what the UI showed.
- **A running database is detected by its command line, not a pid file.**
  A copied backup carries a stale pid file that a recycled pid can make look alive.
  Matching the server's own `--datadir` or `-D` argument has no such false positive.
- **Symlinks are removed as links.**
  The final path component is never resolved, so removing a link cannot reach its target.
- **Trash is the default, permanent delete needs the name typed.**
  Moving to the Trash is reversible but frees no space until it is emptied, so both modes exist and the destructive one asks for more.
- **Cleanup commands are shown, never run.**
  Hints such as `brew cleanup` or `docker system prune` are text for the user to copy.
- **The server is local-only.**
  It binds to `127.0.0.1`, checks the `Host` header, and every request needs a per-run token that is printed in the URL.
- **The UI never uses `innerHTML`.**
  File names are untrusted input, so all text is set through `textContent`.

## Safety model

| Rule | Why |
|---|---|
| Removal is offered only under `$HOME`, `/opt/homebrew` and `/usr/local` | Everything else on the machine is out of scope |
| Top-level folders (`~`, `~/Library`, `~/Documents`, `/opt/homebrew/var`, ...) can be emptied item by item but never removed themselves | One click must not delete a whole library |
| `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.kube` and Keychains are untouchable | Credentials cannot be recovered |
| A directory that is, or contains, the data directory of a running `postgres` or `mysqld` is refused | Deleting live database files corrupts them |
| Permanent delete requires the item's exact name | Prevents an accidental click |

## Known limitations

- The first scan of a large folder is slow, because `du` has to walk it. Results are cached for five minutes.
- Only macOS has been tested. The code uses portable `du` and `find` options, but the hotspot list is macOS-centric.

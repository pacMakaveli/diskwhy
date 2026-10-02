# Install & setup

## Requirements

- Python 3.14 or newer. The interpreter is pinned in `.python-version`.
- macOS is the supported platform. The hotspot list targets a developer Mac.
- No third-party runtime dependencies.

## Quick start

```bash
git clone https://github.com/pacMakaveli/diskwhy.git && cd diskwhy
python3 -m diskwhy
```

This prints a URL containing a one-time token and opens it in your browser.
The token changes on every run, so a bookmarked URL stops working after a restart.

To install the `diskwhy` command instead:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
diskwhy
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check .          # lint (add --fix to auto-correct)
ruff format .         # format
pytest                # tests
```

CI runs the same three commands, so a clean local run is a clean build.

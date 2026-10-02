# AGENTS.md: Diskwhy

Instructions for AI coding agents (Claude Code and friends) working in this repo.
Humans: this is also a fine quick-orientation read.

## Project

- **Name:** diskwhy · **Type:** tool · **License:** Proprietary
- A local web dashboard for developer Macs. It sizes the usual space hogs (Xcode, simulators, package caches, Homebrew, Docker, stale Postgres and MySQL data directories, node_modules), lets you drill into any folder, and removes items behind strict safety guards.

## Conventions (Studio51 standard)

- **Commits:** Conventional Commits, e.g. `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
  Commits must be verified (signed); `main` rejects unverified commits.
- **Branches:** `feature/…`, `fix/…`, `chore/…`. Never commit to `main`; open a
  PR for every change, however small.
- **Pull requests:** keep them atomic (one PR, one thing), give them a clear
  description of what changed and why, and add a `CHANGELOG.md` entry for any
  user-facing change.
- **Changelog:** add a line under **Unreleased** in `CHANGELOG.md` for any user-facing change.
- **Secrets:** never commit credentials, `.env`, or keys.
- **Authorship:** never set an AI tool as the git commit author or co-author,
  and never add an AI `Co-Authored-By` trailer.
- **Writing style:** never use em dashes; use a comma, or reword, instead.
- **Agent files:** this file is the single source of truth for every agent;
  `CLAUDE.md` / `CURSOR.md` / `CODEX.md` are pointers holding only
  agent-specific instructions. Shared guidance goes here.
- **README:** stays minimal — the **Navigation** section declares the
  Studio51 Solutions standard this repo adheres to and links the docs; all
  prose lives in `docs/`, each section in its own file.

### Comments & documentation

Comments are part of the standard — treat them as required, not optional.

- **Document every public method, class, module, and constant** with a comment
  block directly above it: a short sentence on what it is/does, then a description
  of **each parameter** and the **return value**.
- **Separate the prose from the parameter/return tags with one blank comment line**,
  and keep a blank comment line as the last line of a class/module doc block, right
  before the declaration it documents.
- **One sentence per line** — don't hard-wrap a single sentence across lines.
- **Use inline trailing comments** for accessors, struct fields, and grouped
  constants (annotate the line) rather than a comment paragraph above each.
- **Group related members** under a short `# --- Section ---` divider comment.

See the stack section below for the exact doc-comment syntax in this repo's language.

## Stack: Python

- Use a virtual environment: `python3 -m venv .venv && source .venv/bin/activate`.
  The interpreter is pinned in `.python-version`.
- Install: `pip install -r requirements.txt`, or `pip install -e .` when there's a
  `pyproject.toml`.
- Lint & format with **Ruff**: `ruff check .` (`--fix` to auto-correct) and
  `ruff format .`.
- Tests: `pytest`.
- Keep modules importable and side-effect free; put entry points behind
  `if __name__ == "__main__":`.
- Doc comments are **docstrings** in Google style.
  A short summary sentence, then a blank line, then `Args:`, `Returns:` and `Raises:` as they apply.
  One sentence per line.
  Class and module docstrings end with a blank line before the closing quotes.
  Private helpers (leading underscore) and test methods are exempt; test classes and modules still get a one-line docstring.
- Group related members under `# --- Section ---` dividers, and annotate constants with inline trailing comments.
- `safety.py` is the only code allowed to decide whether a path may be removed.
  Anything that deletes must call `removal_blocker` first, and a change to it needs a test that fails without the change.

## Before you finish

- [ ] Tests pass
- [ ] Lint/format clean
- [ ] `CHANGELOG.md` updated (if user-facing)
- [ ] No secrets or large generated artifacts committed
- [ ] README still accurate for any behavior you changed
- [ ] Atomic, clearly described PR off `main`; commits verified (signed)
- [ ] No em dashes; no AI author or `Co-Authored-By` trailer

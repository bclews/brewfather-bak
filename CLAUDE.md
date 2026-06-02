# CLAUDE.md

Guidance for working in this repo. Keep changes consistent with the conventions below.

## What this is

`brewfather-backup` — a CLI that backs up Brewfather recipes, batches, and inventory
to timestamped JSON snapshots. Installs a `brewfather-backup` console script
(`brewfather_backup.cli:app`, built on Typer + Rich).

## Commands

Use the `mise` tasks rather than calling `uv`/`pytest`/`ruff` directly:

- `mise run setup` — sync the virtualenv from the lockfile (`uv sync`)
- `mise run check` — lint + typecheck + test (run this before considering work done)
- `mise run test` — pytest
- `mise run lint` / `mise run fmt` — ruff check / format
- `mise run typecheck` — mypy
- `mise run run -- <args>` — run the CLI (e.g. `mise run run -- run --only recipes -v`)

## Workflow: TDD (red-green-refactor)

This project is developed test-first. For any behavior change:

1. **Red** — write a failing test in `tests/` that pins the desired behavior; run it and confirm it fails for the right reason.
2. **Green** — write the minimum code to make it pass.
3. **Refactor** — clean up production and test code with the suite green.

Finish with `mise run check` (lint + typecheck + test) green before considering work done. Don't add production code without a failing test that motivates it.

## Version control: Jujutsu (`jj`)

This is a **colocated jj + git** repo — use `jj`, not raw `git`, for version control.

- The working copy is itself a commit (`@`); jj auto-tracks new/changed/deleted files, so there is **no staging / `git add`**.
- Describe work with `jj describe -m "..."`; start the next change with `jj new`.
- Commits described `wip:*` are **private** (`git.private-commits`) and are not pushed — use a `wip:` prefix for in-progress snapshots you don't want to publish.
- Push with `jj git push` (creates/updates the git branch). As always, only commit or push when the user asks.

## Conventions

- **Python 3.13+**, `src/` layout (package `brewfather_backup`). `from __future__ import annotations` at the top of each module.
- **mypy is `strict`** (with the pydantic plugin) — keep everything fully typed; no implicit `Any` leaking through public signatures.
- **ruff** enforces `E, F, I, UP, B, SIM` at line length 100. Match modern idioms (e.g. `X | None`, `StrEnum`).
- Tests use **pytest + respx** (mock httpx at the transport layer; don't hit the real API).
- Module docstrings and concise "why" comments are the house style — see `client.py`/`backup.py`. Match that density.

## Architecture

Four modules, each with a clear job:

- `config.py` — `Settings` (pydantic-settings). Reads `BREWFATHER_`-prefixed env vars / `.env`. `user_id` + `api_key` required; everything else defaults.
- `client.py` — thin httpx-based Brewfather API v2 client. Basic auth, pagination (`limit`+`start_after`, page size 50), full-record fetch (`complete=true`), and transient-failure retries (429/5xx + connection errors, honoring `Retry-After`). Raises `BrewfatherError`.
- `backup.py` — `run_backup()` orchestrates the snapshot: fetches records concurrently (`ThreadPoolExecutor`), writes one JSON file per resource, and emits progress via the `ProgressReporter` protocol. `manifest.json` is written **last** as the completeness marker; a failed run `rmtree`s the partial snapshot.
- `cli.py` — Typer command + a Rich-backed reporter.

## Gotchas

- Snapshots are written **directly** into the final timestamped directory (not staged + renamed) so macOS's iCloud File Provider shows files in Finder as they land. Don't "optimize" this back to temp-dir + rename.
- Progress callbacks fire from the **calling thread**, not worker threads, so reporters need not be thread-safe.
- Config overrides from CLI flags are re-validated via `Settings.model_validate(...)` (not `model_copy`) so field constraints still apply.

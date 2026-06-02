# brewfather-backup

[![CI](https://github.com/bclews/brewfather-bak/actions/workflows/ci.yml/badge.svg)](https://github.com/bclews/brewfather-bak/actions/workflows/ci.yml)

Back up your [Brewfather](https://brewfather.app) **recipes**, **batches**, and
**inventory** (fermentables, hops, yeasts, miscs) to timestamped JSON snapshots
on disk.

Each run writes a full, point-in-time snapshot — nothing is overwritten — so you
can keep a history of your brewing data and restore or diff it later.

## Requirements

- [mise](https://mise.jdx.dev) (manages the Python and `uv` versions)
- A Brewfather API key with **read** access to recipes, batches, and inventory

## Setup

```bash
mise install      # provisions Python 3.13 + uv
mise run setup    # creates the virtualenv and installs dependencies
```

### Configure credentials

Generate an API key in Brewfather under **Settings → API** (give it read scopes
for Recipes, Batches, and Inventory), then create a `.env` file:

```bash
cp .env.example .env
# edit .env and fill in BREWFATHER_USER_ID and BREWFATHER_API_KEY
```

Configuration is read from environment variables (prefixed `BREWFATHER_`) or the
`.env` file:

| Variable                     | Required | Default                             |
| ---------------------------- | -------- | ----------------------------------- |
| `BREWFATHER_USER_ID`         | yes      | —                                   |
| `BREWFATHER_API_KEY`         | yes      | —                                   |
| `BREWFATHER_BASE_URL`        | no       | `https://api.brewfather.app/v2`     |
| `BREWFATHER_OUTPUT_DIR`      | no       | `backups`                           |
| `BREWFATHER_REQUEST_TIMEOUT` | no       | `30`                                |

## Usage

```bash
# Full backup of everything
mise run run

# Pass CLI options after `--`
mise run run -- --only inventory          # just inventory
mise run run -- --only recipes --only batches
mise run run -- --out /path/to/backups --verbose
mise run run -- --workers 16              # more concurrent fetches
mise run run -- --quiet                   # no progress spinner (good for cron)
```

| Option            | Description                                              |
| ----------------- | -------------------------------------------------------- |
| `--out PATH`      | Output directory (overrides `BREWFATHER_OUTPUT_DIR`).    |
| `--only GROUP`    | Limit to `recipes`, `batches`, or `inventory`. Repeatable. |
| `--workers N`     | Concurrent record fetches (overrides `BREWFATHER_CONCURRENCY`, default 8). |
| `--verbose`, `-v` | Print a per-resource summary table.                      |
| `--quiet`, `-q`   | Suppress the live progress spinner.                      |

Or invoke the installed script directly:

```bash
uv run brewfather-backup --help
```

### Output layout

```
backups/
└── 2026-06-02T14-30-00Z/
    ├── recipes.json
    ├── batches.json
    ├── inventory/
    │   ├── fermentables.json
    │   ├── hops.json
    │   ├── yeasts.json
    │   └── miscs.json
    └── manifest.json        # timestamp, per-resource counts, base URL, version
```

Records are fetched in **full detail** (the API's `complete=true`), so the
snapshot is a complete backup rather than just list summaries. The client paginates
automatically, fetches records **concurrently** (see `--workers`), and respects
Brewfather's rate limit (500 calls/hour), backing off on `429` responses.

## Development

```bash
mise run test        # pytest (network is mocked with respx — no real API calls)
mise run lint        # ruff
mise run fmt         # ruff format
mise run typecheck   # mypy (strict)
mise run check       # lint + typecheck + test
```

The project follows a TDD workflow and is laid out as a standard `src/` package
managed by `uv`.

# scripts

CLI entrypoints, OALD tooling, and deploy helpers. New functions here do not start with an underscore.

## CLI (`cli.py`)

Exposed as `uv run <name>` via `[project.scripts]` in `pyproject.toml`:

| Command | Role |
| --- | --- |
| `start` / `stop` | Local bot process + `.bot.pid` |
| `migrate` / `check` | Alembic upgrade / metadata match |
| `test` / `format` / `lint` / `typecheck` | Dev quality |
| `oald-import` / `oald-audio` / `oxford-import` | Content tooling |

Pyright covers `tgbot`, `scripts/oald`, and `scripts/cli.py` only.

## OALD tooling (`oald/`)

- Always `uv run migrate` before import/audio scripts. They expect an already-migrated schema and do not create application tables
- `oald-import` — rebuilds `oald_entries` (+ audio URL links) from `data/oald/words.json` (required for cards)
- `oald-audio` — fills prepared voice variants (required for Telegram audio)
- `oxford-import` — optional staging into `oxford_lexical_entries`; runtime bot does not read it
- Engine access goes through `tgbot.db.postgres`, not a second connection layer

## Deploy (`deploy/`)

- `remote_update.sh` runs on the server from GitHub Actions over SSH
- Requires `BOT_IMAGE`, a generated env file, and GHCR login env vars
- Brings up Compose with `--wait` so migrate failure keeps the bot unhealthy
- Do not commit secrets or generated deploy `.env` payloads

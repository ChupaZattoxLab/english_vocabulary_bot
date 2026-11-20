# English vocabulary Telegram bot

Telegram bot that sends OALD-backed vocabulary cards from PostgreSQL.

Code: `tgbot/` (runtime), `scripts/` (CLI and tooling). Agent rules: root `AGENTS.md`.

## Prerequisites

- Docker with Compose
- [uv](https://docs.astral.sh/uv/) (Python 3.14)
- Bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user id (for admin)
- A PostgreSQL dump / seed for the card catalog

## Local setup

Commands are PowerShell-friendly; the same `uv` / `docker compose` names work on Linux/macOS.

### 1. Clone and `.env`

```powershell
cd english_vocabulary_bot
Copy-Item .env.example .env
```

Set at least:

```env
TELEGRAM_BOT_TOKEN=...
OALD_DATABASE_URL=postgresql+psycopg://vocab_app:vocab_dev_password@127.0.0.1:5432/english_vocabulary_oald
```

Defaults match Compose (`vocab_app` / `vocab_dev_password` / `english_vocabulary_oald` on port `5432`).

If host port `5432` is taken, set both before starting Compose:

```env
POSTGRES_PORT=5433
OALD_DATABASE_URL=postgresql+psycopg://vocab_app:vocab_dev_password@127.0.0.1:5433/english_vocabulary_oald
```

`POSTGRES_PORT` is for Compose only. Schedule, templates, and pool settings live in code (`tgbot/**/types.py`), not in `.env`. Admins are `bot_users.role`, not `.env`.

### 2. Place the database seed

Put the dump parts here **before the first** `docker compose up` (init runs once per volume):

```text
data/backups/english_vocabulary_oald_seed_2026-08-01.dump.parts/
  english_vocabulary_oald_seed_2026-08-01.dump.part-001
  english_vocabulary_oald_seed_2026-08-01.dump.part-002
  SHA256SUMS.txt
```

Without them Postgres still starts; restore is skipped and the catalog stays empty until you restore a dump.

To redo init after a missing seed:

```powershell
docker compose down -v
# place seed parts, then:
docker compose up -d
```

`down -v` deletes the local Postgres volume.

### 3. Start Postgres

```powershell
docker compose up -d
docker compose logs -f postgres
```

Wait for `OALD seed restore completed` or `OALD seed parts are missing; skipping automatic restore`, then stop following logs (`Ctrl+C`). Check with `docker compose ps`.

### 4. Install, migrate, run

```powershell
uv sync
uv run migrate
uv run start
```

Always run `uv run migrate` after a fresh volume or an older dump so the schema matches the code.

In Telegram: `/start`, then promote yourself once:

```sql
UPDATE bot_users SET role = 'admin' WHERE telegram_user_id = YOUR_TELEGRAM_ID;
```

Restart the bot so admin commands register, then use `/admin`.

Stop the local process:

```powershell
uv run stop
```

Only one process may poll the same bot token.

## Commands

| Command | What it does |
| --- | --- |
| `uv run start` / `stop` | Run or stop the local bot (PID in `.bot.pid`) |
| `uv run migrate` | Alembic upgrade to head |
| `uv run check` | Metadata matches the migrated DB |
| `uv run test` | Pytest (`TEST_OALD_DATABASE_URL` needed for DB tests) |
| `uv run format` | Ruff format |
| `uv run lint` | Ruff check `--fix` + format check |
| `uv run typecheck` | Pyright on `tgbot`, `scripts/oald`, `scripts/cli.py` |

Push gate (see `.githooks/pre-push`): `uv run ruff check .`, `uv run ruff format --check .`, `uv run typecheck`. `uv run lint` applies fixes; it is not that gate.

## Deploy (GitHub Actions)

Image: `ghcr.io/chupazattoxlab/english_vocabulary_bot`.

Actions → pick a workflow → **Run workflow** → choose the branch under **Use workflow from**.

| Workflow | When you run it |
| --- | --- |
| **test** | Ruff, Pyright, Pytest (Postgres service). On a PR, also by adding the `run-tests` label |
| **publish-image** | Build/push the image and deploy if this commit already has a green **test** run |
| **test-and-publish** | **test**, then publish/deploy in one pipeline |

Merging to `main` needs a green **test** check. After a new commit, remove and re-add `run-tests` to re-run.

Repo Actions secrets are already set. Meaning:

| Secret | Meaning |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Written into the server `.env` on deploy |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres role and database name |
| `SSH_HOST` / `SSH_PORT` / `SSH_USER` / `SSH_PRIVATE_KEY` | SSH into the deploy host |
| `GHCR_USER` / `GHCR_READ_TOKEN` | Docker login on the server (`read:packages`) |

Deploy overwrites `/opt/english_vocabulary_bot/.env` from these secrets, pulls the image, runs `migrate && exec python -m tgbot`, and waits until the bot is healthy.

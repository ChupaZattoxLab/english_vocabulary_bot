# English vocabulary Telegram bot

Offline-friendly Telegram bot that sends OALD-backed vocabulary cards from PostgreSQL.

## Repository layout

```text
tgbot/                 # runtime bot package
  app.py               # aiogram bootstrap / long polling
  secrets.py           # .env / process environment secrets
  bot_config.py        # runtime bot config
  constants.py         # shared domain / runtime constants
  localization/        # Telegram UI strings (default: ru)
  __main__.py          # python -m tgbot
  db/                  # async SQLAlchemy Core access + schema metadata
    mixins/            # users, cards, scheduler, admin queries
    schema/            # SQLAlchemy table metadata (bot/ + oald/)
  delivery/            # card templates, send logic, scheduler
  handlers/            # Telegram user/admin commands and keyboards
scripts/
  cli.py               # uv run start|stop|migrate|test|lint|…
  restore-oald-seed.sh # Docker first-boot seed restore
  oald/                # offline OALD/Oxford build & import helpers
tests/
  tgbot/               # bot unit/integration tests
  oald/                # OALD/Oxford import-script tests
  test_migrations.py   # Alembic baseline tests
migrations/            # Alembic migration revisions
alembic.ini            # Alembic config (script_location → migrations/)
compose.yaml           # local Postgres 16
```

Large artefacts (`data/`, Kaikki `.jsonl`, DB dumps) are **not** published. Keep them
only on your machine or server.

## Prerequisites

- Docker Desktop (or Docker Engine) with Compose
- [uv](https://docs.astral.sh/uv/) (installs/manages a local Python 3.11-3.14 toolchain)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user ID from [@useridinfobot](https://t.me/useridinfobot) (for `/admin`)

## Local setup

Do the steps in order. Commands below are for PowerShell on Windows; on Linux/macOS use the same `uv` / `docker compose` commands.

### 1. Clone and configure env

```powershell
cd english_vocabulary_bot
Copy-Item .env.example .env
```

Edit `.env` with secrets only:

```env
TELEGRAM_BOT_TOKEN=...your token...
TELEGRAM_ADMIN_IDS=123456789
OALD_DATABASE_URL=postgresql+psycopg://vocab_app:vocab_dev_password@127.0.0.1:5432/english_vocabulary_oald
```

Schedule, card templates, and pool sizes live in `tgbot/constants.py` (not `.env`).

`OALD_DATABASE_URL` in `.env.example` matches Compose defaults
(`vocab_app` / `vocab_dev_password` / `english_vocabulary_oald` on port `5432`).

If host port **5432** is already taken (common when a local Postgres is installed),
set **both** of these in `.env` **before** starting Compose:

```env
POSTGRES_PORT=5433
OALD_DATABASE_URL=postgresql+psycopg://vocab_app:vocab_dev_password@127.0.0.1:5433/english_vocabulary_oald
```

`POSTGRES_PORT` is read by Docker Compose only; the bot uses `OALD_DATABASE_URL`.

### 2. Optional: place the OALD seed

For a useful local bot (thousands of ready cards + audio), put the seed parts here
**before the first** `docker compose up` (init runs only once per Docker volume):

```text
data/backups/english_vocabulary_oald_seed_2026-08-01.dump.parts/
  english_vocabulary_oald_seed_2026-08-01.dump.part-001
  english_vocabulary_oald_seed_2026-08-01.dump.part-002
  SHA256SUMS.txt
```

Without these parts Postgres still starts; `scripts/restore-oald-seed.sh` skips restore
and you get an empty schema after migrations. The bot will start, but there will be
nothing to send until you restore a dump or rebuild via `scripts/oald/`.

If the volume was already created without the seed, either add the parts and recreate
the volume, or restore a dump manually:

```powershell
docker compose down -v
# place seed parts, then:
docker compose up -d
```

`down -v` deletes the Postgres volume (all local DB data).

### 3. Start Postgres

```powershell
docker compose up -d
docker compose logs -f postgres
```

Wait for `OALD seed restore completed` or `OALD seed parts are missing; skipping automatic restore`, then `Ctrl+C` (Compose keeps running in the background).

Quick health check:

```powershell
docker compose ps
```

### 4. Install dependencies, migrate, run the bot

```powershell
# once: https://docs.astral.sh/uv/getting-started/installation/
irm https://astral.sh/uv/install.ps1 | iex
# open a new terminal (or refresh PATH), then from the repo root:
uv sync
uv run migrate
uv run start
```

You should see long polling for your bot username. In Telegram: `/start`, then `/admin`
if your ID is in `TELEGRAM_ADMIN_IDS`.

Stop that local bot from another terminal:

```powershell
uv run stop
```

Only one process may poll the same bot token. Stop any server/systemd instance before
running locally, or you will get `TelegramConflictError`.

`uv run migrate` is required both for an empty database and after restoring an older
seed. It adopts a complete legacy schema without deleting OALD data. Import/audio
scripts expect migrations to have run first; they no longer create tables.

## Day-to-day commands

```powershell
uv run start      # run the bot (records PID for stop)
uv run stop       # stop the bot started via start
uv run migrate    # alembic upgrade head
uv run check      # metadata matches migrated DB
uv run test       # pytest
uv run format     # ruff format
uv run lint       # ruff check --fix + format check
uv run typecheck  # pyright on tgbot + scripts/oald
```

Set `TEST_OALD_DATABASE_URL` (same `postgresql+psycopg://` form as
`OALD_DATABASE_URL`) to run PostgreSQL integration tests. The role must be
allowed to create temporary databases. OALD/Oxford import scripts expect
`uv run migrate` first (including `oxford_lexical_entries`).

## Database migrations

Alembic manages all nine application/OALD tables. Canonical table metadata lives in
`tgbot/db/schema/`.

```powershell
uv run migrate
uv run alembic current
uv run alembic history
uv run alembic revision --autogenerate -m "describe schema change"
uv run check
```

Review every autogenerated revision before applying it. On deployment, run
`uv run migrate` before restarting the bot service.

### Server notes

If a remote instance keeps coming back after `kill`, systemd is restarting it:

```bash
systemctl list-units --type=service --all | grep -iE 'vocab|bot|telegram'
sudo systemctl stop vocabulary-bot
sudo systemctl disable vocabulary-bot
ps aux | grep tgbot | grep -v grep
```

To run on the server again later (after `git pull`, `uv sync`, `uv run migrate`):

```bash
sudo systemctl enable --now vocabulary-bot
# or, without systemd:
cd /opt/english_vocabulary_bot
uv sync
uv run migrate
uv run start
```

## pgAdmin

- Host `127.0.0.1`
- Port `5432` (or the `POSTGRES_PORT` from `.env`)
- DB `english_vocabulary_oald`
- User `vocab_app` / password `vocab_dev_password`

## Git history note

Removing `data/` and Kaikki dumps from the current tree does **not** erase them from
old commits. For a truly lean public clone, rewrite history (`git filter-repo`) or
publish a fresh repository without those blobs.

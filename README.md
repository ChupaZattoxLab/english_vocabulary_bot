# English vocabulary Telegram bot

Offline-friendly Telegram bot that sends OALD-backed vocabulary cards from PostgreSQL.

## Repository layout

```text
tgbot/                 # runtime bot package
  app.py               # aiogram bootstrap / long polling
  secrets.py           # .env secrets (pydantic-settings)
  bot_config.py        # runtime bot config from secrets + types
  types.py             # schedule defaults, pool size (tgbot root only)
  localization/        # Telegram UI strings (default: ru)
  __main__.py          # python -m tgbot
  db/
    types.py           # StrEnums + pool/timeouts (db/ only; re-exported via models)
    database.py        # async engine + schema/version checks
    models/            # domain dataclasses (User, Card, …) + public enum re-exports
    queries/           # users, cards, scheduler, admin queries
    tables/            # declarative Mapped models (bot/ + oald/)
      base.py          # DeclarativeBase, tablename helper, varchar_enum
    sync.py            # blocking SQLAlchemy helpers for scripts/tests
  delivery/            # card templates, send logic, scheduler
    types.py           # template paths, DeliveryStatus (delivery/ only)
  handlers/            # Telegram user/admin commands
    keyboard/          # inline keyboards (levels, pronunciation, admin, words)
    helpers.py
    types.py           # admin stats windows (handlers/ only)
scripts/
  cli.py               # uv run start|stop|migrate|test|lint|…
  restore-oald-seed.sh # Docker first-boot seed restore
  oald/                # offline OALD/Oxford build & import helpers
tests/
  tgbot/               # bot unit tests + factories
    factories.py
    queries/           # DB query tests (needs TEST_OALD_DATABASE_URL)
  oald/                # OALD/Oxford import-script tests
migrations/            # Alembic migration revisions
alembic.ini            # Alembic config (script_location → migrations/)
compose.yaml           # local Postgres 16
```

Large artefacts (`data/`, Kaikki `.jsonl`, DB dumps) are **not** published. Keep them
only on your machine or server.

## Prerequisites

- Docker Desktop (or Docker Engine) with Compose
- [uv](https://docs.astral.sh/uv/) (installs/manages a local Python 3.11–3.14 toolchain)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user ID from [@useridinfobot](https://t.me/useridinfobot) (for admin access)

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
OALD_DATABASE_URL=postgresql+psycopg://vocab_app:vocab_dev_password@127.0.0.1:5432/english_vocabulary_oald
```

Schedule defaults live in `tgbot/types.py`; template paths in
`tgbot/delivery/types.py`; DB pool timeouts in `tgbot/db/types.py` (not `.env`).
Each `types.py` is package-private (imported only inside its folder).
Admins are stored in `bot_users.role`, not in `.env`.

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
nothing to send until you restore a dump or rebuild card data (see **Rebuild OALD
content** below).

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

You should see long polling for your bot username. In Telegram: `/start`, then promote
yourself to admin in Postgres (once):

```sql
UPDATE bot_users SET role = 'admin' WHERE telegram_user_id = YOUR_TELEGRAM_ID;
```

Restart the bot so admin commands are registered, then use `/admin`.

Stop that local bot from another terminal:

```powershell
uv run stop
```

Only one process may poll the same bot token. Stop any server/systemd instance before
running locally, or you will get `TelegramConflictError`.

`uv run migrate` is required both for an empty database and after restoring an older
seed. It adopts a complete **legacy** schema (pre-Alembic column layout) without deleting
OALD data, then applies later revisions. Import/audio scripts expect migrations to have
run first; they no longer create tables.

## Day-to-day commands

```powershell
uv run start         # run the bot (records PID for stop)
uv run stop          # stop the bot started via start
uv run migrate       # alembic upgrade head
uv run check         # metadata matches migrated DB
uv run test          # pytest
uv run format        # ruff format
uv run lint          # ruff check --fix + format check
uv run typecheck     # pyright on tgbot + scripts/oald
uv run oald-import   # rebuild oald_entries from data/oald/words.json
uv run oald-audio    # download / transcode pronunciation audio
uv run oxford-import # optional: Oxford API cache → staging table
```

Set `TEST_OALD_DATABASE_URL` (same `postgresql+psycopg://` form as
`OALD_DATABASE_URL`) to run PostgreSQL integration tests. The role must be
allowed to create temporary databases.

## Rebuild OALD content

Prefer the seed dump for local/dev. Use these scripts only when rebuilding from
JSON/cache (or extending the dataset). Always `uv run migrate` first.

| Command | Writes | Needed for the bot? |
| --- | --- | --- |
| `uv run oald-import` | `oald_entries` + audio URL links | **Yes** — this is the card catalog |
| `uv run oald-audio` | `oald_audio_files` / `oald_audio_variants` | **Yes** — Telegram voice messages |
| `uv run oxford-import` | `oxford_lexical_entries` only | **No** — offline staging; runtime never reads it |

```powershell
uv run oald-import --dry-run
uv run oald-import
uv run oald-audio --limit 10
# optional tooling:
uv run oxford-import --dry-run
```

`oald-import` expects `data/oald/words.json`. `oxford-import` expects an Oxford API
cache directory plus `data/enriched/words.json` (both are build artifacts, not shipped
in a lean clone).

## Database migrations

Alembic manages all nine application/OALD tables. Canonical schema lives in
`tgbot/db/tables/` as declarative ORM models (`Mapped` / `mapped_column`). Domain
`StrEnum` values live in `tgbot/db/models/types.py`; columns use `varchar_enum(...)`
(VARCHAR + named CHECK, no PostgreSQL `ENUM` types).

At startup the bot checks that the DB is on Alembic head (`verify_schema`). It does
**not** create or apply migrations by itself.

```powershell
uv run migrate
uv run alembic current
uv run alembic history
uv run alembic revision --autogenerate -m "describe schema change"
uv run check
```

`revision --autogenerate` compares `tgbot/db/tables` metadata to the live database and
writes a draft under `migrations/versions/`. Review every file before applying: it may
suggest noisy renames (for example simple `index=True` → `ix_*` names) that you should
drop if the DB already has equivalent indexes. Then:

```powershell
uv run migrate
```

On deployment, migrations run inside the bot container before the process starts
(`migrate && python -m tgbot`).

## CI/CD (GitHub Actions + Docker)

Repo: `ChupaZattoxLab/english_vocabulary_bot`. Image: `ghcr.io/chupazattoxlab/english_vocabulary_bot`.

### Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| **test** | every pull request + manual button | Ruff, Pyright, Pytest (Postgres service) |
| **publish-image** | manual button | Build/push image + deploy **only if** this commit already has a green **test** run |
| **test-and-publish** | manual button | Run **test**, then publish/deploy in the same pipeline |

For manual runs: Actions → select workflow → **Run workflow** → choose the branch
(Use workflow from) and set `git_ref` to the same branch (usually `main`).

### Branch protection (blocks merge on red tests)

This is configured in the **GitHub repo UI**, not in git files:

1. Repo → **Settings** → **Branches** → **Add branch ruleset** / **Branch protection rule**
2. Branch name pattern: `main`
3. Enable **Require status checks to pass**
4. Add required check: **test** / job `test`
5. Save

Until the first PR has run **test** once, the check name may not appear in the
dropdown — open a draft PR or run **test** once, then select it.

### GitHub Actions secrets

Repo → **Settings** → **Secrets and variables** → **Actions**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | written into server `.env` on deploy |
| `POSTGRES_PASSWORD` | yes | Postgres + `OALD_DATABASE_URL` |
| `POSTGRES_USER` | no | default `vocab_app` |
| `POSTGRES_DB` | no | default `english_vocabulary_oald` |
| `SSH_HOST` | yes | server hostname/IP |
| `SSH_USER` | yes | SSH user (often `root`) |
| `SSH_PRIVATE_KEY` | yes | private key for deploy |
| `SSH_PORT` | no | default `22` |
| `GHCR_READ_TOKEN` | yes for private image pull | PAT with `read:packages` |
| `GHCR_USER` | no | default `chupazattoxlab` |

Create `GHCR_READ_TOKEN`: GitHub → Settings → Developer settings → Personal access
tokens → classic or fine-grained with **read:packages** (and SSO if needed). On the
server, deploy logs into `ghcr.io` with this token before `docker compose pull`.

Deploy **overwrites** `/opt/english_vocabulary_bot/.env` from these secrets. For the
bot container the DB host is the Compose service name `postgres` (not `127.0.0.1`).

### First cutover on the server

Keep the existing Postgres volume (never `docker compose down -v`):

```bash
cd /opt/english_vocabulary_bot
docker compose exec postgres psql -U vocab_app -d english_vocabulary_oald \
  -c 'SELECT COUNT(*) FROM oald_entries;'
sudo systemctl stop vocabulary-bot
sudo systemctl disable vocabulary-bot
```

Then run **test-and-publish** (or **test** then **publish-image**) from GitHub.
Afterward:

```bash
docker compose ps
docker compose logs -f bot
```

### Server notes (legacy systemd)

If an old host unit still restarts a non-Docker bot:

```bash
systemctl list-units --type=service --all | grep -iE 'vocab|bot|telegram'
sudo systemctl stop vocabulary-bot
sudo systemctl disable vocabulary-bot
```

Preferred production path is Compose service `bot` from GHCR (see CI/CD above).

## pgAdmin

- Host `127.0.0.1`
- Port `5432` (or the `POSTGRES_PORT` from `.env`)
- DB `english_vocabulary_oald`
- User `vocab_app` / password `vocab_dev_password`

## Git history note

Removing `data/` and Kaikki dumps from the current tree does **not** erase them from
old commits. For a truly lean public clone, rewrite history (`git filter-repo`) or
publish a fresh repository without those blobs.

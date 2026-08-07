# English vocabulary Telegram bot

Offline-friendly Telegram bot that sends OALD-backed vocabulary cards from PostgreSQL.

## What is in this repo

- `vocabulary_bot/` — Telegram bot (aiogram) and HTML card templates
- `scripts/database/10-restore-oald-seed.sh` — Postgres first-boot hook (optional seed restore)
- `compose.yaml` — local Postgres 16
- `scripts/build_database/` — optional pipeline to rebuild the DB from external sources

Large artefacts (`data/`, Kaikki `.jsonl`, DB dumps) are **not** published. Keep them only on your machine or server.

## Local setup

1. Docker Desktop (or Docker Engine) installed and running.

2. Copy env and fill secrets (never commit `.env`):

```powershell
Copy-Item .env.example .env
```

Set `TELEGRAM_BOT_TOKEN` (BotFather) and `TELEGRAM_ADMIN_IDS` (numeric IDs from `@useridinfobot`).

3. Place the OALD Postgres seed **locally** (not in Git), if you have it:

```text
data/backups/english_vocabulary_oald_seed_2026-08-01.dump.parts/
  english_vocabulary_oald_seed_2026-08-01.dump.part-001
  english_vocabulary_oald_seed_2026-08-01.dump.part-002
  SHA256SUMS.txt
```

Without these parts, Postgres still starts; the init script skips restore and you get an empty DB (or restore a dump another way).

4. Start Postgres:

```powershell
docker compose up -d
docker compose logs -f postgres
```

Wait for `OALD seed restore completed` (or the skip message), then `Ctrl+C`.

If port **5432** is already taken, set in `.env`:

```env
POSTGRES_PORT=5433
OALD_DATABASE_URL=postgresql://vocab_app:vocab_dev_password@127.0.0.1:5433/english_vocabulary_oald
```

5. Install and run the bot:

```powershell
python -m pip install -r requirements.txt
python -m vocabulary_bot
```

Admin UI: `/admin` (only for IDs in `TELEGRAM_ADMIN_IDS`).

Only one process may poll the same bot token. Stop the server instance before running locally.

### Server (systemd)

Unit file: [`deploy/vocabulary-bot.service`](deploy/vocabulary-bot.service).

If the bot keeps coming back after `kill`, systemd is restarting it. On the server:

```bash
# find the unit that owns the process
systemctl status 1718651
# or:
systemctl list-units --type=service --all | grep -iE 'vocab|bot|telegram'
ls /etc/systemd/system/*vocab* /etc/systemd/system/*bot* 2>/dev/null

# stop + disable autostart (use the real unit name)
sudo systemctl stop vocabulary-bot
sudo systemctl disable vocabulary-bot

# confirm nothing is left
ps aux | grep vocabulary_bot | grep -v grep
```

To run on the server again later:

```bash
sudo systemctl enable --now vocabulary-bot
```


## pgAdmin

- Host `127.0.0.1`
- Port `5432` (or `5433` if you remapped)
- DB `english_vocabulary_oald`
- User `vocab_app` / password `vocab_dev_password`

## Git history note

Removing `data/` and Kaikki dumps from the current tree does **not** erase them from old commits. For a truly lean public clone, rewrite history (`git filter-repo`) or publish a fresh repository without those blobs.

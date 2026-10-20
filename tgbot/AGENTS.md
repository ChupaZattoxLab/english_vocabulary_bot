# tgbot

Runtime Telegram bot package (aiogram). Shared engine: `tgbot/db/postgres.py` — used by the bot, scripts, tests, and Alembic. Do not add a second engine factory.

## Layout

- `app.py` / `__main__.py` — bootstrap and long polling
- `secrets.py` — `.env` via pydantic-settings
- `types.py` — schedule defaults and pool size (root package only)
- `db/` — tables, queries, domain models, schema checks
- `delivery/` — card templates, send, scheduler
- `handlers/` — Telegram commands and keyboards
- `localization/ru.py` — Telegram copy

Each `types.py` is package-private: import it only inside its package.

## Database

- Declarative tables in `db/tables/`; domain `StrEnum` values with `varchar_enum` (VARCHAR + CHECK). No PostgreSQL `ENUM` types
- CEFR levels are A1–C1 (`CefrLevel` in `db/types.py`)
- New row IDs: `new_id()` → UUID v7
- Both Alembic blocks in `migrations/env.py` keep `compare_type=True` and `compare_server_default=True`
- Admin access is `bot_users.role`, not `.env`
- Schedule defaults live in `tgbot/types.py`, not `.env`
- Card audio joins keep US/GB as separate laterals; do not pick a cross-variety pair with a single random SQL expression that conflates them
- Do not rename the Oxford JSON key `dialects` or `sqlalchemy.dialects` to “fix” a naming clash

## Code style

- New functions in `tgbot/` do not start with an underscore
- Prefer SQLAlchemy Core `insert` / `update` / `select` in queries; `sa.text()` only for server defaults or expressions with no Core form

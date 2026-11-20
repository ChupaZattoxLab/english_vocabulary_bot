# tests

Pytest suite. Config: `pyproject.toml` (`testpaths = ["tests"]`, `asyncio_mode = auto`).

## How to run

- `uv run test` or `uv run pytest`
- Integration tests that touch PostgreSQL need `TEST_OALD_DATABASE_URL` (same `postgresql+psycopg://` form as `OALD_DATABASE_URL`). The role must be allowed to create temporary databases
- Without that URL, DB tests skip (`tests/support.py`, `tests/tgbot/queries/conftest.py`)
- Required green run for merge is GitHub Actions workflow `test` (label `run-tests` on the PR)

## Layout

- `tests/tgbot/` — bot unit tests, factories, query integration tests
- `tests/oald/` — OALD / Oxford import-script tests
- `tests/support.py` — shared helpers (`TEST_OALD_DATABASE_URL`, temp DB create/destroy)

## Writing tests

- Prefer SQLAlchemy `insert` / `update` for seed data. Use `sa.text()` only when there is no Core form (server default / catalog expression)
- Query integration tests create a disposable database, run Alembic to head, then destroy it — do not point at the developer’s main catalog DB
- Reuse `tests/tgbot/factories.py` and fixtures in `tests/tgbot/queries/conftest.py` instead of duplicating seed graphs
- Keep tests independent of live Telegram; mock the bot API where needed

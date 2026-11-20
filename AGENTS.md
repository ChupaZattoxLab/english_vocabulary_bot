# Agent instructions

Package-specific rules live in `tgbot/AGENTS.md`, `tests/AGENTS.md`, and `scripts/AGENTS.md`. Prefer those when editing inside that tree.

## Commands

Copy from this repo only. Do not invent stacks.

| Intent | Command |
| --- | --- |
| Push gate (same as `.githooks/pre-push`) | `uv run ruff check .` then `uv run ruff format --check .` then `uv run typecheck` |
| Autofix + format check | `uv run lint` — applies fixes; it is not the push gate |
| Format | `uv run format` |
| Tests | `uv run test` — needs PostgreSQL and `TEST_OALD_DATABASE_URL` for DB tests; required CI run is GitHub Actions with the `run-tests` label |
| Migrate / schema check | `uv run migrate` / `uv run check` |
| Bot | `uv run start` / `uv run stop` |

`.agents/` is outside Ruff (`pyproject.toml`). Do not reformat skill text to satisfy the hook.

## Git

Full procedure: `.agents/skills/git-workflow-and-versioning/SKILL.md`.

- One branch per task: `SCRUM-<number>/<english-slug>`
- Several people may share that branch. Before editing, update the branch and `main`, and confirm no conflict. Do not rebase or force-push a shared branch
- Show the diff and message. Create the commit only after the user asks
- A related refactor found during the task stays on that branch as its own commit

## Repo facts

- Python `>=3.14,<3.15` via `uv`
- One PostgreSQL database for bot, OALD catalog, scripts, tests, and Alembic
- Secrets only in `.env`. Do not print them. Do not commit `.env`, `data/`, or `.bot.pid`
- Image: `ghcr.io/chupazattoxlab/english_vocabulary_bot`, tagged by commit SHA (`sha-<12>`); see `.github/workflows/publish-image.yml`
- Deploy runs `migrate && exec python -m tgbot` in the bot container

## Future orientation

Conceptual only — do not implement these early:

- CEFR assessment model
- Website
- Content-service sharing the same PostgreSQL database

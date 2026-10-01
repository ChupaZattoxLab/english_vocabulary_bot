"""Database query helpers composed into Database."""

from tgbot.db.queries.admin import AdminQueries
from tgbot.db.queries.base import DbSession
from tgbot.db.queries.cards import CardsQueries
from tgbot.db.queries.scheduler_runs import SchedulerQueries
from tgbot.db.queries.users import UsersQueries

__all__ = [
    "AdminQueries",
    "CardsQueries",
    "DbSession",
    "SchedulerQueries",
    "UsersQueries",
]

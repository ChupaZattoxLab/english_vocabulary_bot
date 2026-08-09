"""Database query helpers composed into Database."""

from tgbot.db.queries.admin import AdminQueries
from tgbot.db.queries.base import EngineBound
from tgbot.db.queries.cards import CardsQueries
from tgbot.db.queries.scheduler_runs import SchedulerQueries
from tgbot.db.queries.users import UsersQueries

__all__ = [
    "AdminQueries",
    "CardsQueries",
    "EngineBound",
    "SchedulerQueries",
    "UsersQueries",
]

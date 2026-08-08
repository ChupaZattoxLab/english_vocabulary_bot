"""Database method mixins composed into Database."""

from tgbot.db.mixins.admin import AdminMixin
from tgbot.db.mixins.base import PoolBound
from tgbot.db.mixins.cards import CardsMixin
from tgbot.db.mixins.scheduler_runs import SchedulerMixin
from tgbot.db.mixins.users import UsersMixin

__all__ = [
    "AdminMixin",
    "CardsMixin",
    "PoolBound",
    "SchedulerMixin",
    "UsersMixin",
]

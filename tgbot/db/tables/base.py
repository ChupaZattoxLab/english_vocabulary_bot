"""Shared SQLAlchemy declarative base for Alembic-managed tables."""

from __future__ import annotations

import re
from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, declared_attr


def camel_to_snake(name: str) -> str:
    """Convert ``BotUser`` to ``bot_user``."""
    return re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        name,
    ).lower()


def varchar_enum(
    enum_cls: type[PyEnum],
    *,
    name: str,
) -> sa.Enum:
    """VARCHAR-backed enum; ``name`` is also the CHECK constraint name."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Base(DeclarativeBase):
    """Abstract ORM base: ``BotUser`` → ``bot_users`` (snake_case + ``s``).

    Irregular plurals set ``__tablename__`` explicitly on the model class.
    """

    __abstract__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:
        return f"{camel_to_snake(cls.__name__)}s"


metadata = Base.metadata

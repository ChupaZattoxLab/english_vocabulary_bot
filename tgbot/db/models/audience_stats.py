"""Admin audience overview stats."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.engine import RowMapping


@dataclass(frozen=True)
class AudienceStats:
    total_users: int
    active_users: int
    paused_users: int
    blocked_users: int
    new_today: int
    new_week: int
    new_month: int
    levels: dict[str, int]
    dialects: dict[str, int]


def audience_stats_from_row(
    totals: RowMapping,
    levels: Sequence[RowMapping],
    dialects: Sequence[RowMapping],
) -> AudienceStats:
    return AudienceStats(
        total_users=int(totals["total_users"]),
        active_users=int(totals["active_users"]),
        paused_users=int(totals["paused_users"]),
        blocked_users=int(totals["blocked_users"]),
        new_today=int(totals["new_today"]),
        new_week=int(totals["new_week"]),
        new_month=int(totals["new_month"]),
        levels={str(row["level"]): int(row["users"]) for row in levels},
        dialects={
            str(row["dialect"]): int(row["users"]) for row in dialects if row["dialect"]
        },
    )

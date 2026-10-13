"""Admin audience overview stats."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


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
    english_varieties: dict[str, int]


def audience_stats_from_row(
    totals: Mapping[str, Any],
    levels: Sequence[Mapping[str, Any]],
    english_varieties: Sequence[Mapping[str, Any]],
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
        english_varieties={
            str(row["english_variety"]): int(row["users"])
            for row in english_varieties
            if row["english_variety"]
        },
    )

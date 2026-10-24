"""Data classification ordering. The most sensitive input decides the classification of any
derived output (a summary of a confidential file is confidential)."""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import DataClass

# 'unknown' is treated as the most restrictive: it may never leave the workspace.
_RANK = {DataClass.public: 0, DataClass.internal: 1, DataClass.confidential: 2, DataClass.unknown: 3}


def most_sensitive(values: Iterable[str | DataClass]) -> DataClass:
    best = DataClass.public
    for v in values:
        c = DataClass(v)
        if _RANK[c] > _RANK[best]:
            best = c
    return best


def may_leave_without_approval(c: DataClass) -> bool:
    return c in (DataClass.public, DataClass.internal)

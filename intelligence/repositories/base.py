"""Query helpers shared by all repositories: bounded pagination + safe sorting.

No endpoint returns an unbounded table (spec §42).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


@dataclass(slots=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size else 0

    def as_dict(self, serializer: Any) -> dict[str, Any]:
        return {
            "items": [serializer(i) for i in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "pages": self.pages,
        }


def clamp_page_size(page_size: int | None) -> int:
    if not page_size or page_size < 1:
        return DEFAULT_PAGE_SIZE
    return min(page_size, MAX_PAGE_SIZE)


def apply_sort(
    stmt: Select[Any],
    *,
    sort: str | None,
    sortable: dict[str, InstrumentedAttribute[Any]],
    default: str,
) -> Select[Any]:
    """Apply ``?sort=field`` / ``?sort=-field`` restricted to a whitelist of columns."""
    key = sort or default
    direction = desc if key.startswith("-") else asc
    column = sortable.get(key.lstrip("-"), sortable[default.lstrip("-")])
    return stmt.order_by(direction(column), sortable[default.lstrip("-")])


def paginate(session: Session, stmt: Select[Any], *, page: int, page_size: int) -> Page[Any]:
    page = max(page, 1)
    page_size = clamp_page_size(page_size)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars().all()
    return Page(items=list(rows), total=int(total), page=page, page_size=page_size)

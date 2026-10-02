"""Pagination, sorting and filtering helpers (docs/01_ARCHITECTURE.md section 13.5)."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Sequence

from fastapi import Query

from app.core.errors import ValidationError

MAX_PAGE_SIZE = 100


@dataclass(slots=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def paginated(items: Sequence[Any], total_items: int, params: PageParams) -> dict[str, Any]:
    total_pages = ceil(total_items / params.page_size) if params.page_size else 0
    return {
        "items": list(items),
        "page": params.page,
        "page_size": params.page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }


def parse_sort(sort: str | None, allowed: dict[str, Any], default: Any) -> list[Any]:
    """Turn `?sort=-created_at,name` into a list of SQLAlchemy order-by clauses.

    Only allow-listed fields are accepted; anything else is a 422.
    """
    if not sort:
        return [default()]
    clauses: list[Any] = []
    for token in sort.split(","):
        token = token.strip()
        if not token:
            continue
        descending = token.startswith("-")
        field = token[1:] if descending else token
        column = allowed.get(field)
        if column is None:
            raise ValidationError(
                f"Unsupported sort field: {field}",
                errors=[{"field": "sort", "code": "NOT_SORTABLE", "message": f"Cannot sort by {field}"}],
            )
        clauses.append(column.desc() if descending else column.asc())
    if not clauses:
        clauses.append(default())
    return clauses
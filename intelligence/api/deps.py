"""FastAPI dependencies: DB session, pagination params, auth abstraction (spec §39)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from intelligence.config import get_settings
from intelligence.db import get_session as _get_session


def get_session() -> Iterator[Session]:
    yield from _get_session()


SessionDep = Annotated[Session, Depends(get_session)]


@dataclass(slots=True)
class User:
    id: str
    email: str
    roles: tuple[str, ...] = ("analyst",)

    def has_role(self, role: str) -> bool:
        return role in self.roles


def get_current_user(x_user_email: Annotated[str | None, Header()] = None) -> User:
    """V0 auth: a static dev principal (overridable via the ``X-User-Email`` header).

    The rest of the codebase depends only on this abstraction, so a real OIDC/SAML
    provider drops in here without touching routers.
    """
    email = x_user_email or get_settings().dev_user
    roles = ("analyst", "partner") if email.endswith("@chimera.local") else ("analyst",)
    return User(id=email, email=email, roles=roles)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: str):
    def _dep(user: CurrentUser) -> User:
        if not user.has_role(role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {role}")
        return user

    return _dep


@dataclass(slots=True)
class Pagination:
    page: int
    page_size: int
    sort: str | None


def pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    sort: Annotated[str | None, Query()] = None,
) -> Pagination:
    return Pagination(page=page, page_size=page_size, sort=sort)


PaginationDep = Annotated[Pagination, Depends(pagination)]

"""FastAPI dependencies: DB session, authentication (JWT bearer), RBAC permission checks."""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ArgusError, Forbidden, NotFound
from app.core.security import Permission, decode_access_token, has_permission
from app.db.session import get_db
from app.models import OperationalArea, User
from app.services.audit import Actor


class Unauthorized(ArgusError):
    status_code = 401

    def __init__(self, message: str = "Authentication required"):
        super().__init__("unauthorized", message)


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized()
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid token") from exc
    user = db.scalars(select(User).where(User.username == payload.get("sub"))).first()
    if user is None or not user.active:
        raise Unauthorized("Unknown or inactive user")
    return user


def require(permission: Permission) -> Callable[..., Actor]:
    def dep(user: User = Depends(current_user)) -> Actor:
        if not has_permission(user.role, permission):
            raise Forbidden(f"Role {user.role} lacks permission '{permission.value}'", required=permission.value)
        return Actor(user.username, user.role)

    return dep


def area_or_404(area_id: str, db: Session = Depends(get_db)) -> OperationalArea:
    area = db.get(OperationalArea, area_id)
    if area is None:
        raise NotFound("operational area", area_id)
    return area

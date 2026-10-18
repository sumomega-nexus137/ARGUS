"""Authentication primitives (JWT + bcrypt) and role model (RBAC)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
import jwt

from app.core.config import get_settings


class Role(StrEnum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    PLANNER = "PLANNER"
    COMMANDER = "COMMANDER"
    ADMIN = "ADMIN"


class Permission(StrEnum):
    READ = "read"
    FIELD_UPDATE = "field_update"  # observations, road events, task status, resource status
    PLAN_EDIT = "plan_edit"  # plans, scenarios, stress tests, optimization
    PLAN_REVIEW = "plan_review"
    PLAN_APPROVE = "plan_approve"
    DATA_ADMIN = "data_admin"  # imports, conflict resolution, providers
    USER_ADMIN = "user_admin"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.READ},
    Role.OPERATOR: {Permission.READ, Permission.FIELD_UPDATE},
    Role.PLANNER: {Permission.READ, Permission.FIELD_UPDATE, Permission.PLAN_EDIT, Permission.PLAN_REVIEW},
    Role.COMMANDER: {
        Permission.READ,
        Permission.FIELD_UPDATE,
        Permission.PLAN_EDIT,
        Permission.PLAN_REVIEW,
        Permission.PLAN_APPROVE,
        Permission.DATA_ADMIN,
    },
    Role.ADMIN: set(Permission),
}


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(Role(role), set())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(username: str, role: str) -> tuple[str, datetime]:
    s = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=s.jwt_expires_minutes)
    token = jwt.encode({"sub": username, "role": role, "exp": expires}, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, expires


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])

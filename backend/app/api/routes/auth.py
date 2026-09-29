from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Unauthorized, current_user
from app.core.config import get_settings
from app.core.security import ROLE_PERMISSIONS, Role, create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.common import LoginRequest
from app.services.audit import Actor, record

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(u: User) -> dict:
    return {"username": u.username, "full_name": u.full_name, "role": u.role,
            "permissions": sorted(p.value for p in ROLE_PERMISSIONS[Role(u.role)]),
            "preferred_language": u.preferred_language}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    u = db.scalars(select(User).where(User.username == body.username)).first()
    if u is None or not u.active or not verify_password(body.password, u.password_hash):
        raise Unauthorized("Invalid username or password")
    token, exp = create_access_token(u.username, u.role)
    record(db, Actor(u.username, u.role), "USER_LOGIN", "user", u.username, f"{u.username} signed in")
    db.commit()
    return {"token": token, "expires_at": exp.isoformat(), "user": _user_out(u)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_out(user)


@router.get("/demo-users")
def demo_users(db: Session = Depends(get_db)) -> dict:
    """Demo accounts for the login screen (only exposed in DEMO mode)."""
    if not get_settings().demo_mode:
        return {"demo": False, "users": []}
    from app.demo.library import DEMO_PASSWORD

    users = db.scalars(select(User).order_by(User.id)).all()
    return {"demo": True, "password": DEMO_PASSWORD,
            "users": [{"username": u.username, "role": u.role, "full_name": u.full_name} for u in users]}

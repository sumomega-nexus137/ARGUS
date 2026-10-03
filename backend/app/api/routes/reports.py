from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import area_or_404, current_user
from app.api.serialize import clean
from app.db.session import get_db
from app.models import OperationalArea, User
from app.services.reports.builder import build_report
from app.services.reports.html import render

router = APIRouter(prefix="/api/areas/{area_id}", tags=["reports"])


@router.get("/report")
def report(area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    return clean(build_report(db, area))


@router.get("/report.html", response_class=HTMLResponse)
def report_html(lang: str = "kk", area: OperationalArea = Depends(area_or_404), db: Session = Depends(get_db),
                _: User = Depends(current_user)) -> HTMLResponse:
    return HTMLResponse(render(clean(build_report(db, area)), lang))

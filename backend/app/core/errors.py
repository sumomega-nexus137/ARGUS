"""Consistent API error model. Users never see raw stack traces."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger("argus.errors")


class ArgusError(Exception):
    """Domain error with a stable machine code (translated by the frontend)."""

    status_code = 400

    def __init__(self, code: str, message: str = "", status_code: int | None = None, **params: Any):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.params = params
        if status_code is not None:
            self.status_code = status_code


class NotFound(ArgusError):
    status_code = 404

    def __init__(self, entity: str, entity_id: str):
        super().__init__("not_found", f"{entity} '{entity_id}' not found", entity=entity, id=entity_id)


class Forbidden(ArgusError):
    status_code = 403

    def __init__(self, message: str = "Insufficient role for this action", **params: Any):
        super().__init__("forbidden", message, **params)


class Conflict(ArgusError):
    status_code = 409


def _body(code: str, message: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "params": params or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ArgusError)
    async def _argus(_: Request, exc: ArgusError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.params))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_body("validation_error", "Invalid request", {"details": details}))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content=_body("internal_error", "Internal server error"))

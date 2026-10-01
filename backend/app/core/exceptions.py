import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400,
                 detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.detail = detail or {}


def error_response(status: int, code: str, message: str, detail=None, headers=None):
    body = ErrorResponse(code=code, message=message, detail=detail or {})
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed"
        return error_response(exc.status_code, f"HTTP_{exc.status_code}", message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo submitted document text or arbitrary validation context.
        errors = [{"loc": list(e["loc"]), "type": e["type"], "msg": e["msg"]} for e in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errors})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled error: %s %s (%s)", request.method, request.url.path, type(exc).__name__)
        return error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred")

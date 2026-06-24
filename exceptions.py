"""Consistent error responses without exposing internal implementation details."""
import logging
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("cropverse")

def error_response(status_code: int, message: str, details: object = "") -> JSONResponse:
    content = jsonable_encoder(
        {"success": False, "message": message, "details": details},
        custom_encoder={Exception: str},
    )
    return JSONResponse(status_code=status_code, content=content)

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return error_response(422, "Validation failed", exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError):
        logger.exception("Database operation failed", exc_info=exc)
        return error_response(503, "Database service is temporarily unavailable")

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, exc: Exception):
        logger.exception("Unhandled application error", exc_info=exc)
        return error_response(500, "An unexpected server error occurred")

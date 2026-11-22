"""The one place where failures become HTTP: application/problem+json (RFC 9457)
with a stable `code`.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from twochi_api.auth import AuthUnavailableError, MfaRequiredError, UnauthenticatedError
from twochi_application.ports import DatabaseUnavailableError

PROBLEM_JSON = "application/problem+json"


def problem(status: int, code: str, title: str) -> JSONResponse:
    """Build a problem response; the body never echoes request content."""
    return JSONResponse(
        {"type": "about:blank", "title": title, "status": status, "code": code},
        status_code=status,
        media_type=PROBLEM_JSON,
    )


async def _unauthenticated(_request: Request, _error: Exception) -> JSONResponse:
    return problem(401, "unauthenticated", "Authentication required")


async def _mfa_required(_request: Request, _error: Exception) -> JSONResponse:
    return problem(403, "mfa_required", "Second factor required")


async def _auth_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    return problem(503, "auth_unavailable", "Authentication temporarily unavailable")


async def _database_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    return problem(503, "database_unavailable", "Game data temporarily unavailable")


async def _invalid_request(_request: Request, _error: Exception) -> JSONResponse:
    return problem(422, "invalid_request", "Invalid request")


async def _http_error(_request: Request, error: Exception) -> JSONResponse:
    status = error.status_code if isinstance(error, HTTPException) else 500
    codes = {404: "not_found", 405: "method_not_allowed"}
    return problem(status, codes.get(status, "http_error"), "Request failed")


async def _internal_error(_request: Request, _error: Exception) -> JSONResponse:
    return problem(500, "internal_error", "Unexpected error")


def install(app: FastAPI) -> None:
    """Register every exception handler on the app."""
    app.add_exception_handler(UnauthenticatedError, _unauthenticated)
    app.add_exception_handler(MfaRequiredError, _mfa_required)
    app.add_exception_handler(AuthUnavailableError, _auth_unavailable)
    app.add_exception_handler(DatabaseUnavailableError, _database_unavailable)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    # Anything else: a problem without details; Starlette still logs the traceback.
    app.add_exception_handler(Exception, _internal_error)

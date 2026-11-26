"""The one place where failures become HTTP: application/problem+json (RFC 9457)
with a stable `code`.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from twochi_api.auth import AuthUnavailableError, MfaRequiredError, UnauthenticatedError
from twochi_application.care import IdempotencyKeyReusedError, PetNotFoundError
from twochi_application.ports import DatabaseUnavailableError
from twochi_application.tastes import NoPetYetError
from twochi_domain.catalog import InvalidItemError

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


async def _pet_not_found(_request: Request, _error: Exception) -> JSONResponse:
    # The same answer for an unknown pet and another couple's: nothing leaks.
    return problem(404, "not_found", "Request failed")


async def _idempotency_key_reused(_request: Request, _error: Exception) -> JSONResponse:
    # A key names one request: reusing it for another is a client error, not a retry.
    return problem(422, "idempotency_key_reused", "Idempotency key already used")


async def _no_pet_yet(_request: Request, _error: Exception) -> JSONResponse:
    # Tastes belong to the caller's pet, born when both people have signed up.
    return problem(409, "no_pet_yet", "The pet has not been born yet")


async def _invalid_item(_request: Request, _error: Exception) -> JSONResponse:
    return _invalid_item_problem()


def _invalid_item_problem() -> JSONResponse:
    # Missing, unknown, of the other kind or given to an action that takes none.
    return problem(422, "invalid_item", "Item does not fit the action")


async def _invalid_request(_request: Request, error: Exception) -> JSONResponse:
    # An item the catalogue does not know fails the schema's enum before reaching the
    # use case: it is the same problem as an item the use case refuses.
    if isinstance(error, RequestValidationError) and _only_item_key(error):
        return _invalid_item_problem()
    return problem(422, "invalid_request", "Invalid request")


def _only_item_key(error: RequestValidationError) -> bool:
    # In a care action's body, or in the path of a taste.
    item_key = {("body", "item_key"), ("path", "item_key")}
    locations = [tuple(detail.get("loc", ())) for detail in error.errors()]
    return bool(locations) and all(loc[:2] in item_key for loc in locations)


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
    app.add_exception_handler(PetNotFoundError, _pet_not_found)
    app.add_exception_handler(IdempotencyKeyReusedError, _idempotency_key_reused)
    app.add_exception_handler(NoPetYetError, _no_pet_yet)
    app.add_exception_handler(InvalidItemError, _invalid_item)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(HTTPException, _http_error)
    # Anything else: a problem without details; Starlette still logs the traceback.
    app.add_exception_handler(Exception, _internal_error)

"""Routes. Each one translates the request, calls one function and translates back."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel, Field

from twochi_api import problems
from twochi_api.auth import AUTH_HEADER, Principal, TokenVerifier
from twochi_api.home import HomeOut, home_out
from twochi_application.actors import UserActor
from twochi_application.home import get_home
from twochi_application.ports import Clock, Database
from twochi_domain.ids import UserId


class Health(BaseModel):
    status: str


class PingRequest(BaseModel):
    nonce: str = Field(min_length=1, max_length=64)


class PingResponse(BaseModel):
    user_id: UUID
    nonce: str


def create_app(verifier: TokenVerifier, *, db: Database, clock: Clock) -> FastAPI:
    """Build the API around a configured token verifier and the adapters it needs."""
    app = FastAPI(
        title="Twochi API",
        openapi_url="/api/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    problems.install(app)

    def principal(
        auth: Annotated[str | None, Header(alias=AUTH_HEADER)] = None,
    ) -> Principal:
        return verifier.verify(auth)

    # The decorators register the routes; pyright cannot see that use.
    @app.get("/api/health")
    def health() -> Health:  # pyright: ignore[reportUnusedFunction]
        return Health(status="ok")

    # Edge probe: an authenticated POST with a body proves the CloudFront to Lambda
    # path (OAC signature, body hash, JWT header) end to end. The smoke test uses it.
    @app.post("/api/pings")
    def ping(  # pyright: ignore[reportUnusedFunction]
        body: PingRequest, who: Annotated[Principal, Depends(principal)]
    ) -> PingResponse:
        return PingResponse(user_id=who.user_id, nonce=body.nonce)

    @app.get("/api/home")
    async def home(  # pyright: ignore[reportUnusedFunction]
        who: Annotated[Principal, Depends(principal)],
    ) -> HomeOut:
        actor = UserActor(user_id=UserId(who.user_id), claims=who.claims)
        return home_out(await get_home(actor, db=db, clock=clock))

    return app

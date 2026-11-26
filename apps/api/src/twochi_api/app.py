"""Routes. Each one translates the request, calls one function and translates back."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel, Field

from twochi_api import problems
from twochi_api.auth import AUTH_HEADER, Principal, TokenVerifier
from twochi_api.care import CareActionIn, CareActionOut, care_command, care_out
from twochi_api.home import HomeOut, home_out
from twochi_api.tastes import (
    TasteIn,
    TasteOut,
    TastesOut,
    rate_command,
    taste_out,
    tastes_out,
)
from twochi_application.actors import UserActor
from twochi_application.care import apply_care_action
from twochi_application.home import get_home
from twochi_application.ports import Clock, Database
from twochi_application.tastes import get_my_tastes, rate_taste
from twochi_domain.catalog import ActivityKey, FoodKey
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

    # Casa is one view per caller: `me` keeps the collection noun plural.
    @app.get("/api/homes/me")
    async def home(  # pyright: ignore[reportUnusedFunction]
        who: Annotated[Principal, Depends(principal)],
    ) -> HomeOut:
        return home_out(await get_home(_actor(who), db=db, clock=clock))

    # A refusal is a 200 with `applied: false`: the front animates it.
    @app.post("/api/pets/{pet_id}/care-actions")
    async def care_action(  # pyright: ignore[reportUnusedFunction]
        pet_id: UUID,
        body: CareActionIn,
        who: Annotated[Principal, Depends(principal)],
    ) -> CareActionOut:
        command = care_command(_actor(who), pet_id, body)
        return care_out(await apply_care_action(command, db=db, clock=clock))

    # Only the caller's own tastes: no route reads those of the pet they care for,
    # which they discover by caring (ADR 0015).
    @app.get("/api/tastes/me")
    async def my_tastes(  # pyright: ignore[reportUnusedFunction]
        who: Annotated[Principal, Depends(principal)],
    ) -> TastesOut:
        return tastes_out(await get_my_tastes(_actor(who), db=db))

    @app.put("/api/tastes/me/{item_key}")
    async def rate(  # pyright: ignore[reportUnusedFunction]
        item_key: FoodKey | ActivityKey,
        body: TasteIn,
        who: Annotated[Principal, Depends(principal)],
    ) -> TasteOut:
        command = rate_command(_actor(who), item_key, body)
        return taste_out(await rate_taste(command, db=db, clock=clock))

    return app


def _actor(who: Principal) -> UserActor:
    return UserActor(user_id=UserId(who.user_id), claims=who.claims)

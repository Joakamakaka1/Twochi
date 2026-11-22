"""Care actions at the HTTP edge: the request and response schemas and their mapping."""

from uuid import UUID

from pydantic import BaseModel, Field

from twochi_api.home import PetOut, pet_out
from twochi_application.actors import UserActor
from twochi_application.care import ApplyCareAction, CareResult
from twochi_domain.care import CareAction, Rejection
from twochi_domain.ids import PetId
from twochi_domain.needs import Need


class CareActionIn(BaseModel):
    """One tap: the front reuses its key when it retries that same tap."""

    action: CareAction
    # The front sends a UUID; anything outside this set, such as a NUL, is refused
    # here instead of failing in Postgres.
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class CareActionOut(BaseModel):
    """Applied with its deltas, or refused with its reason; the pet as it is now."""

    applied: bool
    rejection: Rejection | None
    deltas: dict[Need, float]
    pet: PetOut


def care_command(actor: UserActor, pet_id: UUID, body: CareActionIn) -> ApplyCareAction:
    """Map the request to the use case's command."""
    return ApplyCareAction(
        actor=actor,
        pet_id=PetId(pet_id),
        action=body.action,
        idempotency_key=body.idempotency_key,
    )


def care_out(result: CareResult) -> CareActionOut:
    """Map the use case's result to the response."""
    return CareActionOut(
        applied=result.applied,
        rejection=result.rejection,
        deltas=dict(result.deltas),
        pet=pet_out(result.pet),
    )

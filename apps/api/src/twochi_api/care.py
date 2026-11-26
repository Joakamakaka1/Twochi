"""Care actions at the HTTP edge: the request and response schemas and their mapping."""

from uuid import UUID

from pydantic import BaseModel, Field

from twochi_api.home import PetOut, pet_out
from twochi_application.actors import UserActor
from twochi_application.care import ApplyCareAction, CareResult
from twochi_domain.care import CareAction, Reaction, Rejection, SicknessChange
from twochi_domain.catalog import ActivityKey, Affinity, FoodKey
from twochi_domain.ids import PetId
from twochi_domain.needs import Need


class CareActionIn(BaseModel):
    """One tap: the front reuses its key when it retries that same tap."""

    action: CareAction
    # The front sends a UUID; anything outside this set, such as a NUL, is refused
    # here instead of failing in Postgres.
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    # Required to feed (a food) and to play (an activity); forbidden in the rest.
    item_key: FoodKey | ActivityKey | None = None


class ReactionOut(BaseModel):
    """How the pet took what it was given: the item and its affinity right then."""

    item_key: FoodKey | ActivityKey
    affinity: Affinity


class CareActionOut(BaseModel):
    """Applied with its deltas, or refused with its reason; the pet as it is now.

    `reaction` comes with feeding and playing; `sickness` when the action left the pet
    sick or healed it.
    """

    applied: bool
    rejection: Rejection | None
    deltas: dict[Need, float]
    reaction: ReactionOut | None
    sickness: SicknessChange | None
    pet: PetOut


def care_command(actor: UserActor, pet_id: UUID, body: CareActionIn) -> ApplyCareAction:
    """Map the request to the use case's command."""
    return ApplyCareAction(
        actor=actor,
        pet_id=PetId(pet_id),
        action=body.action,
        idempotency_key=body.idempotency_key,
        item_key=body.item_key,
    )


def care_out(result: CareResult) -> CareActionOut:
    """Map the use case's result to the response."""
    return CareActionOut(
        applied=result.applied,
        rejection=result.rejection,
        deltas=dict(result.deltas),
        reaction=_reaction_out(result.reaction),
        sickness=result.sickness,
        pet=pet_out(result.pet),
    )


def _reaction_out(reaction: Reaction | None) -> ReactionOut | None:
    if reaction is None:
        return None
    return ReactionOut(item_key=reaction.item, affinity=reaction.affinity)

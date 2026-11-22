"""Caring for a pet: the engine decides each action and the transaction keeps it."""

from collections.abc import Mapping
from dataclasses import dataclass

from twochi_application.actors import UserActor
from twochi_application.ports import CareRecord, Clock, Database
from twochi_domain.care import (
    PETTING_WINDOW,
    Applied,
    CareAction,
    Rejected,
    Rejection,
    apply_care,
)
from twochi_domain.errors import TwochiError
from twochi_domain.ids import PetId
from twochi_domain.needs import Need
from twochi_domain.pet import PetReading, read_pet


@dataclass(frozen=True, slots=True)
class ApplyCareAction:
    """A care action a person asks for; the key makes a retry apply only once."""

    actor: UserActor
    pet_id: PetId
    action: CareAction
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CareResult:
    """What happened, and the pet as it is now.

    A refusal is a result, not an error: it travels to the front, which animates it.
    """

    applied: bool
    rejection: Rejection | None
    deltas: Mapping[Need, float]
    pet: PetReading


class PetNotFoundError(TwochiError):
    """The pet does not exist for the actor: unknown, or another couple's under RLS."""


async def apply_care_action(
    cmd: ApplyCareAction, *, db: Database, clock: Clock
) -> CareResult:
    """Apply a care action once per key, with the pet locked while the engine decides.

    The lock comes before the key lookup, so two requests with the same key queue on
    the pet and the second finds the first one's event. A refusal writes nothing, so
    deciding it again on a retry is harmless.
    """
    async with db.transaction(cmd.actor) as tx:
        pet = await tx.pets.lock(cmd.pet_id)
        if pet is None:
            raise PetNotFoundError
        now = clock.now()
        stored = await tx.events.stored_care(pet.id, cmd.idempotency_key)
        if stored is not None:
            return CareResult(
                applied=True, rejection=None, deltas=stored, pet=read_pet(pet, now=now)
            )
        recent = await tx.events.effective_pets_since(pet.id, now - PETTING_WINDOW)
        outcome = apply_care(
            pet,
            cmd.action,
            actor=cmd.actor.user_id,
            now=now,
            recent_effective_pets=recent,
        )
        match outcome:
            case Rejected(reason=reason):
                return CareResult(
                    applied=False,
                    rejection=reason,
                    deltas={},
                    pet=read_pet(pet, now=now),
                )
            case Applied():
                await tx.pets.save(outcome.pet)
                await tx.events.record_care(
                    CareRecord(
                        actor=cmd.actor.user_id,
                        action=cmd.action,
                        applied=outcome,
                    ),
                    at=now,
                    idempotency_key=cmd.idempotency_key,
                )
                return CareResult(
                    applied=True,
                    rejection=None,
                    deltas=outcome.deltas,
                    pet=read_pet(outcome.pet, now=now),
                )

"""Casa at the HTTP edge: the response schema and its mapping from the domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from twochi_api.catalogue import AffinityByItem
from twochi_application.home import Home
from twochi_domain.needs import Need
from twochi_domain.pet import Mood, NeedReading, PetReading


class NeedOut(BaseModel):
    """A need at `updated_at` and its hourly change; the front interpolates."""

    value: float
    updated_at: datetime
    rate_per_hour: float


class NeedsOut(BaseModel):
    hunger: NeedOut
    energy: NeedOut
    hygiene: NeedOut
    fun: NeedOut
    affection: NeedOut


class PetOut(BaseModel):
    id: UUID
    name: str
    model_key: str
    asleep: bool
    mood: Mood
    needs: NeedsOut


class HomePetOut(PetOut):
    """The pet the caller cares for, with the tastes they discovered: for each item they
    gave, the affinity seen the last time. Never the pet's tastes (ADR 0015)."""

    discovered: AffinityByItem


class HomeOut(BaseModel):
    """The pet the caller cares for, or null until both people have arrived."""

    pet: HomePetOut | None


def home_out(home: Home) -> HomeOut:
    """Map the use case's result to the response."""
    if home.pet is None:
        return HomeOut(pet=None)
    pet = pet_out(home.pet)
    return HomeOut(pet=HomePetOut(**dict(pet), discovered=dict(home.discovered)))


def pet_out(reading: PetReading) -> PetOut:
    """Map a pet as read at a moment to its response, the same in Casa and care."""

    def need(which: Need) -> NeedOut:
        return _need_out(reading.needs[which])

    return PetOut(
        id=reading.pet.id,
        name=reading.pet.name,
        model_key=reading.pet.model_key,
        asleep=reading.asleep,
        mood=reading.mood,
        needs=NeedsOut(
            hunger=need(Need.HUNGER),
            energy=need(Need.ENERGY),
            hygiene=need(Need.HYGIENE),
            fun=need(Need.FUN),
            affection=need(Need.AFFECTION),
        ),
    )


def _need_out(reading: NeedReading) -> NeedOut:
    return NeedOut(
        value=reading.value,
        updated_at=reading.updated_at,
        rate_per_hour=reading.rate_per_hour,
    )

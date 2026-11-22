"""Casa at the HTTP edge: the response schema and its mapping from the domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

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


class HomeOut(BaseModel):
    """The pet the caller cares for, or null until both people have arrived."""

    pet: PetOut | None


def home_out(home: Home) -> HomeOut:
    """Map the use case's result to the response."""
    return HomeOut(pet=None if home.pet is None else _pet_out(home.pet))


def _pet_out(reading: PetReading) -> PetOut:
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

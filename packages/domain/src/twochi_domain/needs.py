"""Pet needs and how they change with real time.

The stored state is the last value and when it was written; the current value is
computed on read from the hourly rates, so no job updates needs in the background.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from twochi_domain.errors import TwochiError

MIN_VALUE = 0.0
MAX_VALUE = 100.0


class Need(StrEnum):
    """One of the five needs a pet has."""

    HUNGER = "hunger"
    ENERGY = "energy"
    HYGIENE = "hygiene"
    FUN = "fun"
    AFFECTION = "affection"


class NonUtcDatetimeError(TwochiError):
    """A datetime reached the domain naive or in a timezone other than UTC."""


class NeedValueOutOfRangeError(TwochiError):
    """A stored need value is outside [0, 100]."""


@dataclass(frozen=True, slots=True)
class NeedState:
    """Last stored value of a need and when it was written."""

    value: float
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.updated_at)
        if not MIN_VALUE <= self.value <= MAX_VALUE:
            raise NeedValueOutOfRangeError(self.value)


@dataclass(frozen=True, slots=True)
class _HourlyRate:
    awake: float
    asleep: float


# Starting numbers as signed change per hour; they move to the versioned catalogue.
_RATES = MappingProxyType(
    {
        Need.HUNGER: _HourlyRate(awake=-6, asleep=-3),
        Need.ENERGY: _HourlyRate(awake=-5, asleep=12),
        Need.HYGIENE: _HourlyRate(awake=-3, asleep=-3),
        Need.FUN: _HourlyRate(awake=-7, asleep=-3.5),
        Need.AFFECTION: _HourlyRate(awake=-4, asleep=-4),
    }
)


def rate_per_hour(need: Need, *, asleep: bool) -> float:
    """Signed change per hour of a need while the pet is awake or asleep."""
    rate = _RATES[need]
    return rate.asleep if asleep else rate.awake


def current_value(
    need: Need, state: NeedState, *, now: datetime, asleep: bool
) -> float:
    """Value of a need at `now`, from its stored state, clamped to [0, 100]."""
    _require_utc(now)
    # A clock behind the stored timestamp means no time passed, not time running back.
    elapsed = max(now - state.updated_at, timedelta(0))
    hours = elapsed / timedelta(hours=1)
    value = state.value + rate_per_hour(need, asleep=asleep) * hours
    return min(MAX_VALUE, max(MIN_VALUE, value))


def _require_utc(moment: datetime) -> None:
    if moment.utcoffset() != timedelta(0):
        raise NonUtcDatetimeError(moment)

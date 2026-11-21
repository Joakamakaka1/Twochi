from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from twochi_domain.errors import TwochiError
from twochi_domain.needs import Need, NeedState, current_value, rate_per_hour

T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
NAIVE = datetime(2026, 11, 21, 12, 0)  # noqa: DTZ001 - the input under test


def hours(n: float) -> timedelta:
    return timedelta(hours=n)


def test_there_are_five_needs() -> None:
    assert {need.value for need in Need} == {
        "hunger",
        "energy",
        "hygiene",
        "fun",
        "affection",
    }


@pytest.mark.parametrize(
    ("need", "awake", "asleep"),
    [
        (Need.HUNGER, -6, -3),
        (Need.ENERGY, -5, 12),
        (Need.HYGIENE, -3, -3),
        (Need.FUN, -7, -3.5),
        (Need.AFFECTION, -4, -4),
    ],
)
def test_hourly_rates_follow_the_starting_numbers(
    need: Need, awake: float, asleep: float
) -> None:
    assert rate_per_hour(need, asleep=False) == awake
    assert rate_per_hour(need, asleep=True) == asleep


def test_hunger_drops_six_points_per_hour_awake() -> None:
    state = NeedState(value=100, updated_at=T0)

    assert current_value(Need.HUNGER, state, now=T0 + hours(2), asleep=False) == 88


def test_energy_recovers_while_asleep() -> None:
    state = NeedState(value=40, updated_at=T0)

    assert current_value(Need.ENERGY, state, now=T0 + hours(30 / 60), asleep=True) == 46


def test_value_stops_at_zero() -> None:
    state = NeedState(value=10, updated_at=T0)

    assert current_value(Need.FUN, state, now=T0 + hours(3), asleep=False) == 0


def test_value_stops_at_one_hundred() -> None:
    state = NeedState(value=95, updated_at=T0)

    assert current_value(Need.ENERGY, state, now=T0 + hours(8), asleep=True) == 100


def test_now_before_the_stored_update_keeps_the_stored_value() -> None:
    state = NeedState(value=50, updated_at=T0)

    assert current_value(Need.HUNGER, state, now=T0 - hours(1), asleep=False) == 50


def test_naive_now_is_rejected() -> None:
    state = NeedState(value=50, updated_at=T0)

    with pytest.raises(TwochiError):
        current_value(Need.HUNGER, state, now=NAIVE, asleep=False)


def test_non_utc_now_is_rejected() -> None:
    state = NeedState(value=50, updated_at=T0)
    madrid = timezone(timedelta(hours=1))

    with pytest.raises(TwochiError):
        current_value(Need.HUNGER, state, now=T0.astimezone(madrid), asleep=False)


def test_naive_updated_at_is_rejected() -> None:
    with pytest.raises(TwochiError):
        NeedState(value=50, updated_at=NAIVE)


@pytest.mark.parametrize("value", [-0.1, 100.1])
def test_stored_value_outside_the_range_is_rejected(value: float) -> None:
    with pytest.raises(TwochiError):
        NeedState(value=value, updated_at=T0)


needs = st.sampled_from(Need)
values = st.floats(min_value=0, max_value=100)
elapsed = st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=400))


@given(need=needs, value=values, passed=elapsed, asleep=st.booleans())
def test_value_never_leaves_its_range(
    need: Need, value: float, passed: timedelta, asleep: bool
) -> None:
    state = NeedState(value=value, updated_at=T0)

    assert 0 <= current_value(need, state, now=T0 + passed, asleep=asleep) <= 100


@given(need=needs, value=values, earlier=elapsed, later=elapsed)
def test_time_passing_awake_never_raises_a_need(
    need: Need, value: float, earlier: timedelta, later: timedelta
) -> None:
    earlier, later = sorted((earlier, later))
    state = NeedState(value=value, updated_at=T0)

    before = current_value(need, state, now=T0 + earlier, asleep=False)
    after = current_value(need, state, now=T0 + later, asleep=False)

    assert after <= before <= value


@given(
    need=st.sampled_from([n for n in Need if n is not Need.ENERGY]),
    value=values,
    passed=elapsed,
)
def test_time_passing_asleep_raises_only_energy(
    need: Need, value: float, passed: timedelta
) -> None:
    state = NeedState(value=value, updated_at=T0)

    assert current_value(need, state, now=T0 + passed, asleep=True) <= value

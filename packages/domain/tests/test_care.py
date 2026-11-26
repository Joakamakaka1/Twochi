from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from statistics import fmean
from uuid import UUID

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from twochi_domain.care import (
    RULES_VERSION,
    Applied,
    CareAction,
    Reaction,
    Rejected,
    Rejection,
    SicknessChange,
    apply_care,
    checked_item,
)
from twochi_domain.catalog import CATALOG, Affinity, InvalidItemError, ItemKey, ItemKind
from twochi_domain.ids import CoupleId, PetId, UserId
from twochi_domain.needs import Need, NeedState
from twochi_domain.pet import Pet, read_pet

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
ALICE = UserId(UUID("00000000-0000-4000-8000-00000000000a"))
BRUNO = UserId(UUID("00000000-0000-4000-8000-00000000000b"))


# What each test gives when the action needs an item: a food or an activity.
ITEM = {CareAction.FEED: ItemKey.PIZZA, CareAction.PLAY: ItemKey.BALL}


def hours(n: float) -> timedelta:
    return timedelta(hours=n)


def pet(
    *,
    values: Mapping[Need, float] | None = None,
    asleep: bool = False,
    sick_since: datetime | None = None,
    updated_at: datetime = T0,
) -> Pet:
    """A pet that represents Alice and Bruno cares for; needs at 80 unless given."""
    given = values or {}
    return Pet(
        id=PetId(UUID("00000000-0000-4000-8000-0000000000f1")),
        couple_id=CoupleId(UUID("00000000-0000-4000-8000-0000000000c1")),
        represents_user_id=ALICE,
        caretaker_user_id=BRUNO,
        name="Ali",
        model_key="ali",
        needs={
            need: NeedState(value=given.get(need, 80), updated_at=updated_at)
            for need in Need
        },
        asleep=asleep,
        sick_since=sick_since,
    )


def test_feeding_adds_thirty_to_hunger() -> None:
    outcome = apply_care(
        pet(values={Need.HUNGER: 50}),
        CareAction.FEED,
        item=ItemKey.PIZZA,
        actor=BRUNO,
        now=T0,
        recent_effective_pets=0,
    )

    assert isinstance(outcome, Applied)
    assert outcome.pet.needs[Need.HUNGER] == NeedState(value=80, updated_at=T0)
    assert outcome.deltas == {Need.HUNGER: 30}


def apply(
    subject: Pet,
    action: CareAction,
    *,
    affinity: Affinity = Affinity.NEUTRAL,
    actor: UserId = BRUNO,
    now: datetime = T0,
    recent_effective_pets: int = 0,
) -> Applied:
    outcome = apply_care(
        subject,
        action,
        item=ITEM.get(action),
        affinity=affinity,
        actor=actor,
        now=now,
        recent_effective_pets=recent_effective_pets,
    )
    assert isinstance(outcome, Applied)
    return outcome


def values_of(subject: Pet) -> dict[Need, float]:
    return {need: state.value for need, state in subject.needs.items()}


def test_playing_adds_twenty_five_fun_and_costs_eight_energy() -> None:
    outcome = apply(pet(values={Need.FUN: 50, Need.ENERGY: 50}), CareAction.PLAY)

    assert values_of(outcome.pet)[Need.FUN] == 75
    assert values_of(outcome.pet)[Need.ENERGY] == 42
    assert outcome.deltas == {Need.FUN: 25, Need.ENERGY: -8}


def test_petting_adds_fifteen_affection() -> None:
    outcome = apply(pet(values={Need.AFFECTION: 50}), CareAction.PET)

    assert values_of(outcome.pet)[Need.AFFECTION] == 65
    assert outcome.deltas == {Need.AFFECTION: 15}
    assert outcome.effective


def test_the_fourth_effective_petting_in_an_hour_applies_with_no_effect() -> None:
    outcome = apply(
        pet(values={Need.AFFECTION: 50}), CareAction.PET, recent_effective_pets=3
    )

    assert values_of(outcome.pet)[Need.AFFECTION] == 50
    assert outcome.deltas == {Need.AFFECTION: 0}
    assert not outcome.effective


def test_bathing_leaves_hygiene_full() -> None:
    outcome = apply(pet(values={Need.HYGIENE: 12}), CareAction.BATHE)

    assert values_of(outcome.pet)[Need.HYGIENE] == 100
    assert outcome.deltas == {Need.HYGIENE: 88}


def test_sleeping_and_waking_only_change_the_sleep_state() -> None:
    asleep = apply(pet(), CareAction.SLEEP)
    awake = apply(asleep.pet, CareAction.WAKE)

    assert asleep.pet.asleep
    assert not awake.pet.asleep
    assert asleep.deltas == {}
    assert awake.deltas == {}
    assert values_of(awake.pet) == dict.fromkeys(Need, 80)


def test_feeding_a_nearly_full_pet_stops_at_one_hundred() -> None:
    outcome = apply(pet(values={Need.HUNGER: 90}), CareAction.FEED)

    assert values_of(outcome.pet)[Need.HUNGER] == 100
    assert outcome.deltas == {Need.HUNGER: 10}


def test_playing_with_exactly_ten_energy_is_allowed() -> None:
    outcome = apply(pet(values={Need.ENERGY: 10}), CareAction.PLAY)

    assert values_of(outcome.pet)[Need.ENERGY] == 2


def test_needs_are_brought_to_now_before_the_effect() -> None:
    # Two hours awake: hunger 80 -> 68, then +30.
    outcome = apply(pet(), CareAction.FEED, now=T0 + hours(2))

    assert outcome.pet.needs[Need.HUNGER] == NeedState(98, T0 + hours(2))
    assert outcome.pet.needs[Need.FUN] == NeedState(66, T0 + hours(2))
    assert outcome.deltas == {Need.HUNGER: 30}


def test_waking_keeps_the_hours_slept_at_the_asleep_rates() -> None:
    # Asleep two hours: energy 80 + 24 = 100 (clamped), hunger 80 - 6 = 74.
    outcome = apply(pet(asleep=True), CareAction.WAKE, now=T0 + hours(2))

    assert values_of(outcome.pet)[Need.ENERGY] == 100
    assert values_of(outcome.pet)[Need.HUNGER] == 74


def rejection_of(
    subject: Pet, action: CareAction, *, actor: UserId = BRUNO
) -> Rejection | None:
    outcome = apply_care(
        subject,
        action,
        item=ITEM.get(action),
        actor=actor,
        now=T0,
        recent_effective_pets=0,
    )
    return outcome.reason if isinstance(outcome, Rejected) else None


@pytest.mark.parametrize("action", list(CareAction))
def test_only_the_caretaker_may_care(action: CareAction) -> None:
    # Alice is the person this pet represents: she never cares for it.
    assert rejection_of(pet(), action, actor=ALICE) is Rejection.NOT_CARETAKER


@pytest.mark.parametrize(
    "action",
    [CareAction.FEED, CareAction.PLAY, CareAction.PET, CareAction.BATHE],
)
def test_an_asleep_pet_refuses_everything_but_waking(action: CareAction) -> None:
    assert rejection_of(pet(asleep=True), action) is Rejection.ASLEEP


def test_sleeping_an_asleep_pet_is_refused() -> None:
    assert rejection_of(pet(asleep=True), CareAction.SLEEP) is Rejection.ALREADY_ASLEEP


def test_waking_an_awake_pet_is_refused() -> None:
    assert rejection_of(pet(), CareAction.WAKE) is Rejection.ALREADY_AWAKE


def test_a_tired_pet_refuses_to_play() -> None:
    tired = pet(values={Need.ENERGY: 9.9})

    assert rejection_of(tired, CareAction.PLAY) is Rejection.TOO_TIRED


def test_tiredness_is_judged_at_now() -> None:
    # Energy 12 at T0 is 7 one hour later awake.
    outcome = apply_care(
        pet(values={Need.ENERGY: 12}),
        CareAction.PLAY,
        item=ItemKey.BALL,
        actor=BRUNO,
        now=T0 + hours(1),
        recent_effective_pets=0,
    )

    assert outcome == Rejected(Rejection.TOO_TIRED)


def test_not_being_the_caretaker_comes_before_any_other_reason() -> None:
    asleep_and_tired = pet(asleep=True, values={Need.ENERGY: 0})

    assert rejection_of(asleep_and_tired, CareAction.PLAY, actor=ALICE) is (
        Rejection.NOT_CARETAKER
    )


def test_being_asleep_comes_before_being_tired() -> None:
    asleep_and_tired = pet(asleep=True, values={Need.ENERGY: 0})

    assert rejection_of(asleep_and_tired, CareAction.PLAY) is Rejection.ASLEEP


def test_caring_for_a_pet_whose_average_fell_below_twenty_marks_it_sick() -> None:
    # Average 19 before feeding, 25 after: it is the average before that counts.
    outcome = apply(pet(values=dict.fromkeys(Need, 19)), CareAction.FEED)

    assert outcome.pet.sick_since == T0


def test_an_average_of_exactly_twenty_does_not_mark_it_sick() -> None:
    outcome = apply(pet(values=dict.fromkeys(Need, 20)), CareAction.FEED)

    assert outcome.pet.sick_since is None


def test_a_pet_already_sick_keeps_the_moment_it_fell_sick() -> None:
    since = T0 - hours(5)
    outcome = apply(
        pet(values=dict.fromkeys(Need, 10), sick_since=since), CareAction.FEED
    )

    assert outcome.pet.sick_since == since


def test_a_sick_pet_heals_when_every_need_is_back_to_forty() -> None:
    values = dict.fromkeys(Need, 40.0) | {Need.HYGIENE: 0.0}
    outcome = apply(pet(values=values, sick_since=T0 - hours(5)), CareAction.BATHE)

    assert outcome.pet.sick_since is None


def test_a_sick_pet_stays_sick_while_one_need_is_below_forty() -> None:
    # Average 76, but fun is still at 39.
    values = dict.fromkeys(Need, 100.0) | {Need.FUN: 39.0, Need.HUNGER: 41.0}
    outcome = apply(pet(values=values, sick_since=T0 - hours(5)), CareAction.FEED)

    assert outcome.pet.sick_since == T0 - hours(5)


def test_falling_sick_is_noted_on_the_action() -> None:
    outcome = apply(pet(values=dict.fromkeys(Need, 19)), CareAction.FEED)

    assert outcome.sickness is SicknessChange.FELL_SICK


def test_healing_is_noted_on_the_action() -> None:
    values = dict.fromkeys(Need, 40.0) | {Need.HYGIENE: 0.0}
    outcome = apply(pet(values=values, sick_since=T0 - hours(5)), CareAction.BATHE)

    assert outcome.sickness is SicknessChange.HEALED


@pytest.mark.parametrize(
    ("values", "sick_since"),
    [
        (dict.fromkeys(Need, 80.0), None),
        (dict.fromkeys(Need, 10.0), T0 - hours(5)),
    ],
    ids=["stays-healthy", "stays-sick"],
)
def test_no_change_of_sickness_notes_nothing(
    values: dict[Need, float], sick_since: datetime | None
) -> None:
    outcome = apply(pet(values=values, sick_since=sick_since), CareAction.FEED)

    assert outcome.sickness is None


# Tastes: the catalogue and the affinity of the pet with what it is given.


def test_the_catalogue_holds_twelve_foods_and_six_activities() -> None:
    foods = {key for key, kind in CATALOG.items() if kind is ItemKind.FOOD}
    activities = {key for key, kind in CATALOG.items() if kind is ItemKind.ACTIVITY}

    assert foods == {
        "tortilla",
        "paella",
        "pizza",
        "burger",
        "sushi",
        "pasta",
        "tacos",
        "salad",
        "broccoli",
        "strawberries",
        "ice_cream",
        "chocolate",
    }
    assert activities == {
        "ball",
        "video_games",
        "dance",
        "reading",
        "drawing",
        "puzzle",
    }
    assert set(CATALOG) == set(ItemKey)


def test_the_rules_version_moved_on_with_the_tastes() -> None:
    assert RULES_VERSION == "2026-11-26"


@pytest.mark.parametrize(
    ("affinity", "hunger", "affection"),
    [
        (Affinity.HATES, 10, None),
        (Affinity.DISLIKES, 20, None),
        (Affinity.NEUTRAL, 30, None),
        (Affinity.LIKES, 35, 5),
        (Affinity.LOVES, 45, 10),
    ],
)
def test_a_food_raises_hunger_by_how_much_the_pet_likes_it(
    affinity: Affinity, hunger: float, affection: float | None
) -> None:
    outcome = apply(
        pet(values=dict.fromkeys(Need, 50)), CareAction.FEED, affinity=affinity
    )

    expected = {Need.HUNGER: hunger}
    if affection is not None:
        expected[Need.AFFECTION] = affection
    assert outcome.deltas == expected
    assert values_of(outcome.pet)[Need.HUNGER] == 50 + hunger
    assert outcome.reaction == Reaction(item=ItemKey.PIZZA, affinity=affinity)


@pytest.mark.parametrize(
    ("affinity", "fun", "affection"),
    [
        (Affinity.HATES, 5, None),
        (Affinity.DISLIKES, 15, None),
        (Affinity.NEUTRAL, 25, None),
        (Affinity.LIKES, 30, 5),
        (Affinity.LOVES, 40, 10),
    ],
)
def test_an_activity_raises_fun_by_how_much_the_pet_likes_it(
    affinity: Affinity, fun: float, affection: float | None
) -> None:
    outcome = apply(
        pet(values=dict.fromkeys(Need, 50)), CareAction.PLAY, affinity=affinity
    )

    expected = {Need.FUN: fun, Need.ENERGY: -8}
    if affection is not None:
        expected[Need.AFFECTION] = affection
    assert outcome.deltas == expected
    assert outcome.reaction == Reaction(item=ItemKey.BALL, affinity=affinity)


def test_an_item_the_pet_was_never_rated_on_is_neutral() -> None:
    outcome = apply_care(
        pet(values={Need.HUNGER: 50}),
        CareAction.FEED,
        item=ItemKey.SUSHI,
        actor=BRUNO,
        now=T0,
        recent_effective_pets=0,
    )

    assert isinstance(outcome, Applied)
    assert outcome.deltas == {Need.HUNGER: 30}
    assert outcome.reaction == Reaction(item=ItemKey.SUSHI, affinity=Affinity.NEUTRAL)


def test_disgust_is_applied_not_refused() -> None:
    outcome = apply_care(
        pet(values={Need.HUNGER: 50}),
        CareAction.FEED,
        item=ItemKey.BROCCOLI,
        affinity=Affinity.HATES,
        actor=BRUNO,
        now=T0,
        recent_effective_pets=0,
    )

    assert isinstance(outcome, Applied)
    assert values_of(outcome.pet)[Need.HUNGER] == 60


def test_a_favourite_stops_at_one_hundred() -> None:
    nearly_full = pet(values={Need.HUNGER: 90, Need.AFFECTION: 95})

    outcome = apply(nearly_full, CareAction.FEED, affinity=Affinity.LOVES)

    assert values_of(outcome.pet)[Need.HUNGER] == 100
    assert values_of(outcome.pet)[Need.AFFECTION] == 100
    assert outcome.deltas == {Need.HUNGER: 10, Need.AFFECTION: 5}


@pytest.mark.parametrize("action", [CareAction.PET, CareAction.BATHE, CareAction.SLEEP])
def test_actions_without_an_item_have_no_reaction(action: CareAction) -> None:
    assert apply(pet(), action).reaction is None


@pytest.mark.parametrize(
    ("action", "item"),
    [
        (CareAction.FEED, None),
        (CareAction.FEED, ItemKey.BALL),
        (CareAction.PLAY, None),
        (CareAction.PLAY, ItemKey.PIZZA),
        (CareAction.PET, ItemKey.PIZZA),
        (CareAction.WAKE, ItemKey.BALL),
    ],
    ids=[
        "feed-nothing",
        "feed-an-activity",
        "play-nothing",
        "play-a-food",
        "pet-a-food",
        "wake-an-activity",
    ],
)
def test_an_item_that_does_not_fit_the_action_is_an_error(
    action: CareAction, item: ItemKey | None
) -> None:
    with pytest.raises(InvalidItemError):
        apply_care(
            pet(), action, item=item, actor=BRUNO, now=T0, recent_effective_pets=0
        )


def test_an_item_key_is_checked_against_the_catalogue_and_the_action() -> None:
    assert checked_item(CareAction.FEED, "ice_cream") is ItemKey.ICE_CREAM
    assert checked_item(CareAction.PLAY, "puzzle") is ItemKey.PUZZLE
    assert checked_item(CareAction.BATHE, None) is None


@pytest.mark.parametrize(
    ("action", "key"),
    [
        (CareAction.FEED, "caviar"),
        (CareAction.FEED, "ball"),
        (CareAction.FEED, None),
        (CareAction.PET, "pizza"),
    ],
    ids=["unknown", "wrong-kind", "missing", "not-wanted"],
)
def test_an_item_key_that_does_not_fit_is_an_error(
    action: CareAction, key: str | None
) -> None:
    with pytest.raises(InvalidItemError):
        checked_item(action, key)


need_values = st.fixed_dictionaries(
    {need: st.floats(min_value=0, max_value=100) for need in Need}
)
some_time = st.timedeltas(timedelta(0), timedelta(days=3))


@given(
    values=need_values,
    asleep=st.booleans(),
    action=st.sampled_from(CareAction),
    passed=some_time,
    recent_effective_pets=st.integers(0, 10),
)
def test_no_action_ever_takes_a_need_out_of_its_range(
    values: dict[Need, float],
    asleep: bool,
    action: CareAction,
    passed: timedelta,
    recent_effective_pets: int,
) -> None:
    outcome = apply_care(
        pet(values=values, asleep=asleep),
        action,
        item=ITEM.get(action),
        actor=BRUNO,
        now=T0 + passed,
        recent_effective_pets=recent_effective_pets,
    )

    if isinstance(outcome, Applied):
        assert all(0 <= s.value <= 100 for s in outcome.pet.needs.values())


@given(
    values=need_values,
    asleep=st.booleans(),
    action=st.sampled_from(CareAction),
    passed=some_time,
    recent_effective_pets=st.integers(0, 10),
)
def test_applying_and_reading_at_the_same_moment_agree(
    values: dict[Need, float],
    asleep: bool,
    action: CareAction,
    passed: timedelta,
    recent_effective_pets: int,
) -> None:
    before = pet(values=values, asleep=asleep)
    now = T0 + passed
    outcome = apply_care(
        before,
        action,
        item=ITEM.get(action),
        actor=BRUNO,
        now=now,
        recent_effective_pets=recent_effective_pets,
    )
    assume(isinstance(outcome, Applied))
    assert isinstance(outcome, Applied)

    read_before = read_pet(before, now=now).needs
    read_after = read_pet(outcome.pet, now=now).needs
    for need in Need:
        expected = read_before[need].value + outcome.deltas.get(need, 0)
        assert read_after[need].value == pytest.approx(expected)


def average_at(subject: Pet, moment: datetime) -> float:
    return fmean(r.value for r in read_pet(subject, now=moment).needs.values())


@given(values=need_values, asleep=st.booleans(), first=some_time, then=some_time)
def test_the_average_never_rises_between_two_actions(
    values: dict[Need, float], asleep: bool, first: timedelta, then: timedelta
) -> None:
    subject = pet(values=values, asleep=asleep)
    earlier, later = T0 + first, T0 + first + then
    falling = [n for n in Need if n is not Need.ENERGY]
    # Asleep, energy gains 12 per hour while the other four lose 13.5 together, but a
    # need that reached 0 stops losing: past that point the average may rise (below).
    assume(
        not asleep
        or all(read_pet(subject, now=later).needs[n].value > 0 for n in falling)
    )

    assert average_at(subject, later) <= average_at(subject, earlier) + 1e-9


def test_asleep_with_needs_at_zero_the_average_rises_with_energy() -> None:
    # The known exception to the property above, kept visible on purpose.
    subject = pet(values=dict.fromkeys(Need, 0), asleep=True)

    assert average_at(subject, T0 + hours(1)) == pytest.approx(12 / 5)


@given(values=need_values, passed=some_time)
def test_bathing_always_leaves_hygiene_exactly_full(
    values: dict[Need, float], passed: timedelta
) -> None:
    outcome = apply(pet(values=values), CareAction.BATHE, now=T0 + passed)

    assert outcome.pet.needs[Need.HYGIENE].value == 100

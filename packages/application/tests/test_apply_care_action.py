"""`apply_care_action` against local Supabase with real RLS; only the clock is fake."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import API_URL, Couples, TestCouple

from twochi_application.actors import UserActor
from twochi_application.care import (
    ApplyCareAction,
    CareResult,
    IdempotencyKeyReusedError,
    PetNotFoundError,
    apply_care_action,
)
from twochi_application.home import get_home
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_data.events import UnexpectedPayloadError
from twochi_domain.care import CareAction, Reaction, Rejection, SicknessChange
from twochi_domain.catalog import Affinity, InvalidItemError, ItemKey
from twochi_domain.ids import PetId
from twochi_domain.needs import Need

pytestmark = pytest.mark.anyio

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)

# What the caretaker gives when the test does not say: a food or an activity.
DEFAULT_ITEM = {CareAction.FEED: "pizza", CareAction.PLAY: "ball"}


@pytest.fixture
async def db() -> AsyncIterator[PostgresDatabase]:
    database = PostgresDatabase(API_URL, require_tls=False)
    try:
        yield database
    finally:
        await database.close()


async def care(
    db: PostgresDatabase,
    actor: UserActor,
    pet_id: PetId,
    action: CareAction,
    *,
    at: datetime = T0,
    key: str | None = None,
    item: str | None = None,
) -> CareResult:
    command = ApplyCareAction(
        actor=actor,
        pet_id=pet_id,
        action=action,
        idempotency_key=key or str(uuid4()),
        item_key=item or DEFAULT_ITEM.get(action),
    )
    return await apply_care_action(command, db=db, clock=FixedClock(at))


async def bruno_cares(
    db: PostgresDatabase,
    couple: TestCouple,
    action: CareAction,
    *,
    at: datetime = T0,
    key: str | None = None,
    item: str | None = None,
) -> CareResult:
    """Bruno, the caretaker, acts on the pet that represents Alice."""
    actor = couple.actor(couple.bruno)
    return await care(
        db, actor, couple.pet_of_alice.id, action, at=at, key=key, item=item
    )


async def needs_seen_by_bruno(
    db: PostgresDatabase, couple: TestCouple, *, at: datetime = T0
) -> Mapping[Need, float]:
    home = await get_home(couple.actor(couple.bruno), db=db, clock=FixedClock(at))
    assert home.pet is not None
    return {need: reading.value for need, reading in home.pet.needs.items()}


@pytest.mark.parametrize(
    ("action", "deltas"),
    [
        (CareAction.FEED, {Need.HUNGER: 30}),
        (CareAction.PLAY, {Need.FUN: 25, Need.ENERGY: -8}),
        (CareAction.PET, {Need.AFFECTION: 15}),
        (CareAction.BATHE, {Need.HYGIENE: 50}),
        (CareAction.SLEEP, {}),
    ],
)
async def test_the_caretaker_applies_each_action(
    couples: Couples,
    db: PostgresDatabase,
    action: CareAction,
    deltas: Mapping[Need, float],
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 50), updated_at=T0
    )

    result = await bruno_cares(db, couple, action)

    assert result.applied
    assert result.rejection is None
    assert result.deltas == deltas
    assert result.pet.pet.id == couple.pet_of_alice.id
    expected = {need: 50 + deltas.get(need, 0) for need in Need}
    assert {n: r.value for n, r in result.pet.needs.items()} == expected
    assert await needs_seen_by_bruno(db, couple) == expected


async def test_a_pet_put_to_sleep_wakes_only_when_woken(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)

    await bruno_cares(db, couple, CareAction.SLEEP)
    # Two hours asleep: energy 80 + 24 stops at 100, hunger 80 - 6 = 74.
    woken = await bruno_cares(db, couple, CareAction.WAKE, at=T0 + timedelta(hours=2))

    assert woken.applied
    assert not woken.pet.asleep
    assert woken.pet.needs[Need.ENERGY].value == 100
    assert woken.pet.needs[Need.HUNGER].value == 74


async def test_the_pet_that_represents_you_is_not_yours_to_care_for(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    alice = couple.actor(couple.alice)

    result = await care(db, alice, couple.pet_of_alice.id, CareAction.FEED)

    assert not result.applied
    assert result.rejection is Rejection.NOT_CARETAKER
    assert result.deltas == {}
    assert await needs_seen_by_bruno(db, couple) == dict.fromkeys(Need, 80)


@pytest.mark.parametrize(
    ("first", "then", "reason"),
    [
        (CareAction.SLEEP, CareAction.FEED, Rejection.ASLEEP),
        (CareAction.SLEEP, CareAction.SLEEP, Rejection.ALREADY_ASLEEP),
        (None, CareAction.WAKE, Rejection.ALREADY_AWAKE),
    ],
)
async def test_the_engine_refuses_what_the_sleep_state_forbids(
    couples: Couples,
    db: PostgresDatabase,
    first: CareAction | None,
    then: CareAction,
    reason: Rejection,
) -> None:
    couple = await couples.create(updated_at=T0)
    if first is not None:
        await bruno_cares(db, couple, first)

    result = await bruno_cares(db, couple, then)

    assert not result.applied
    assert result.rejection is reason


async def test_a_tired_pet_refuses_to_play(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.ENERGY: 9}, updated_at=T0)

    result = await bruno_cares(db, couple, CareAction.PLAY)

    assert result.rejection is Rejection.TOO_TIRED
    assert result.pet.needs[Need.ENERGY].value == 9
    assert await needs_seen_by_bruno(db, couple) == {
        **dict.fromkeys(Need, 80),
        Need.ENERGY: 9,
    }


async def test_a_refusal_writes_nothing_so_its_key_stays_free(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await bruno_cares(db, couple, CareAction.SLEEP)
    refused = await bruno_cares(db, couple, CareAction.FEED, key="tap-1")
    await bruno_cares(db, couple, CareAction.WAKE)

    retried = await bruno_cares(db, couple, CareAction.FEED, key="tap-1")

    assert refused.rejection is Rejection.ASLEEP
    assert retried.applied
    assert retried.deltas == {Need.HUNGER: 20}


async def test_the_same_key_twice_applies_once_and_returns_the_stored_result(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 20}, updated_at=T0)

    first = await bruno_cares(db, couple, CareAction.FEED, key="double-tap")
    second = await bruno_cares(db, couple, CareAction.FEED, key="double-tap")

    assert first.applied
    assert second.applied
    assert second.deltas == {Need.HUNGER: 30}
    assert second.pet.needs[Need.HUNGER].value == 50
    assert (await needs_seen_by_bruno(db, couple))[Need.HUNGER] == 50


async def test_the_fourth_effective_petting_in_an_hour_has_no_effect(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(
        needs_of_alices_pet={Need.AFFECTION: 0}, updated_at=T0
    )
    minutes = [0, 10, 20, 30]
    results = [
        await bruno_cares(db, couple, CareAction.PET, at=T0 + timedelta(minutes=m))
        for m in minutes
    ]

    assert [r.deltas[Need.AFFECTION] for r in results[:3]] == [15, 15, 15]
    fourth = results[3]
    assert fourth.applied
    assert fourth.deltas == {Need.AFFECTION: 0}


async def test_pettings_without_effect_do_not_count_toward_the_limit(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(
        needs_of_alices_pet={Need.AFFECTION: 0}, updated_at=T0
    )
    for m in [0, 10, 20, 30]:
        await bruno_cares(db, couple, CareAction.PET, at=T0 + timedelta(minutes=m))

    # At 1:05 the last hour holds two effective pettings (0:10 and 0:20) and the one
    # without effect (0:30): the limit of three is not reached.
    later = await bruno_cares(
        db, couple, CareAction.PET, at=T0 + timedelta(hours=1, minutes=5)
    )

    assert later.deltas == {Need.AFFECTION: 15}


async def test_two_actions_at_once_on_the_same_pet_both_apply(
    couples: Couples,
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 20}, updated_at=T0)
    # Two connections, as two Lambda containers would hold.
    first, second = (
        PostgresDatabase(API_URL, require_tls=False),
        PostgresDatabase(API_URL, require_tls=False),
    )
    try:
        results = await asyncio.gather(
            bruno_cares(first, couple, CareAction.FEED),
            bruno_cares(second, couple, CareAction.FEED),
        )
        seen = await needs_seen_by_bruno(first, couple)
    finally:
        await first.close()
        await second.close()

    assert all(result.applied for result in results)
    assert seen[Need.HUNGER] == 80


async def test_another_couples_pet_does_not_exist_for_you(
    couples: Couples, db: PostgresDatabase
) -> None:
    ours = await couples.create(updated_at=T0)
    theirs = await couples.create(updated_at=T0)

    with pytest.raises(PetNotFoundError):
        await care(db, ours.actor(ours.bruno), theirs.pet_of_alice.id, CareAction.FEED)

    assert await needs_seen_by_bruno(db, theirs) == dict.fromkeys(Need, 80)


async def test_a_token_without_the_second_factor_finds_no_pet(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    aal1 = couple.actor(couple.bruno, aal="aal1")

    with pytest.raises(PetNotFoundError):
        await care(db, aal1, couple.pet_of_alice.id, CareAction.FEED)

    assert await needs_seen_by_bruno(db, couple) == dict.fromkeys(Need, 80)


async def test_an_unknown_pet_is_not_found(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)

    with pytest.raises(PetNotFoundError):
        await care(db, couple.actor(couple.bruno), PetId(uuid4()), CareAction.FEED)


async def test_a_double_tap_at_once_applies_once(couples: Couples) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 20}, updated_at=T0)
    first, second = (
        PostgresDatabase(API_URL, require_tls=False),
        PostgresDatabase(API_URL, require_tls=False),
    )
    try:
        results = await asyncio.gather(
            bruno_cares(first, couple, CareAction.FEED, key="same-tap"),
            bruno_cares(second, couple, CareAction.FEED, key="same-tap"),
        )
        seen = await needs_seen_by_bruno(first, couple)
    finally:
        await first.close()
        await second.close()

    assert [r.deltas for r in results] == [{Need.HUNGER: 30}, {Need.HUNGER: 30}]
    assert seen[Need.HUNGER] == 50


async def test_a_key_reused_for_another_action_is_refused_and_changes_nothing(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HYGIENE: 10}, updated_at=T0)
    await bruno_cares(db, couple, CareAction.FEED, key="reused")

    with pytest.raises(IdempotencyKeyReusedError):
        await bruno_cares(db, couple, CareAction.BATHE, key="reused")

    assert (await needs_seen_by_bruno(db, couple))[Need.HYGIENE] == 10


async def test_someone_else_replaying_a_key_is_refused(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await bruno_cares(db, couple, CareAction.FEED, key="bruno-tap")
    alice = couple.actor(couple.alice)

    with pytest.raises(IdempotencyKeyReusedError):
        await care(db, alice, couple.pet_of_alice.id, CareAction.FEED, key="bruno-tap")


async def test_a_key_already_used_by_a_system_event_is_not_a_care_replay(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await couples.admin.execute(
        "insert into app.pet_events "
        "(couple_id, pet_id, source, action, rules_version, idempotency_key) "
        "values ($1, $2, 'system', 'birth', 'test', 'birth-key')",
        couple.id,
        couple.pet_of_alice.id,
    )

    with pytest.raises(IdempotencyKeyReusedError):
        await bruno_cares(db, couple, CareAction.FEED, key="birth-key")


# Tastes: what the caretaker gives, and how the pet takes it.


async def rate(
    couples: Couples, couple: TestCouple, pet_id: PetId, item: str, affinity: int
) -> None:
    """Set a pet's affinity with an item, as the person it represents would."""
    await couples.admin.execute(
        "insert into app.item_affinities (couple_id, pet_id, item_key, affinity) "
        "values ($1, $2, $3, $4) "
        "on conflict (pet_id, item_key) do update set affinity = excluded.affinity",
        couple.id,
        pet_id,
        item,
        affinity,
    )


@pytest.mark.parametrize(
    ("affinity", "deltas"),
    [
        (Affinity.HATES, {Need.HUNGER: 10}),
        (Affinity.DISLIKES, {Need.HUNGER: 20}),
        (Affinity.NEUTRAL, {Need.HUNGER: 30}),
        (Affinity.LIKES, {Need.HUNGER: 35, Need.AFFECTION: 5}),
        (Affinity.LOVES, {Need.HUNGER: 45, Need.AFFECTION: 10}),
    ],
)
async def test_a_food_feeds_by_the_pets_affinity_with_it(
    couples: Couples,
    db: PostgresDatabase,
    affinity: Affinity,
    deltas: Mapping[Need, float],
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 50), updated_at=T0
    )
    await rate(couples, couple, couple.pet_of_alice.id, "tortilla", affinity)

    result = await bruno_cares(db, couple, CareAction.FEED, item="tortilla")

    assert result.applied
    assert result.deltas == deltas
    assert result.reaction == Reaction(item=ItemKey.TORTILLA, affinity=affinity)
    expected = {need: 50 + deltas.get(need, 0) for need in Need}
    assert await needs_seen_by_bruno(db, couple) == expected


@pytest.mark.parametrize(
    ("affinity", "deltas"),
    [
        (Affinity.HATES, {Need.FUN: 5, Need.ENERGY: -8}),
        (Affinity.DISLIKES, {Need.FUN: 15, Need.ENERGY: -8}),
        (Affinity.NEUTRAL, {Need.FUN: 25, Need.ENERGY: -8}),
        (Affinity.LIKES, {Need.FUN: 30, Need.ENERGY: -8, Need.AFFECTION: 5}),
        (Affinity.LOVES, {Need.FUN: 40, Need.ENERGY: -8, Need.AFFECTION: 10}),
    ],
)
async def test_an_activity_entertains_by_the_pets_affinity_with_it(
    couples: Couples,
    db: PostgresDatabase,
    affinity: Affinity,
    deltas: Mapping[Need, float],
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 50), updated_at=T0
    )
    await rate(couples, couple, couple.pet_of_alice.id, "dance", affinity)

    result = await bruno_cares(db, couple, CareAction.PLAY, item="dance")

    assert result.deltas == deltas
    assert result.reaction == Reaction(item=ItemKey.DANCE, affinity=affinity)


async def test_an_item_never_rated_is_neutral(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 50}, updated_at=T0)
    # The other pet's taste is not this one's.
    await rate(couples, couple, couple.pet_of_bruno.id, "sushi", Affinity.LOVES)

    result = await bruno_cares(db, couple, CareAction.FEED, item="sushi")

    assert result.deltas == {Need.HUNGER: 30}
    assert result.reaction == Reaction(item=ItemKey.SUSHI, affinity=Affinity.NEUTRAL)


async def test_disgust_is_applied(couples: Couples, db: PostgresDatabase) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 50}, updated_at=T0)
    await rate(couples, couple, couple.pet_of_alice.id, "broccoli", Affinity.HATES)

    result = await bruno_cares(db, couple, CareAction.FEED, item="broccoli")

    assert result.applied
    assert result.rejection is None
    assert result.reaction == Reaction(item=ItemKey.BROCCOLI, affinity=Affinity.HATES)
    assert (await needs_seen_by_bruno(db, couple))[Need.HUNGER] == 60


@pytest.mark.parametrize(
    ("action", "item"),
    [
        (CareAction.FEED, "caviar"),
        (CareAction.FEED, "ball"),
        (CareAction.PLAY, "pizza"),
        (CareAction.BATHE, "pizza"),
    ],
    ids=["unknown", "an-activity-to-eat", "a-food-to-play", "an-item-to-bathe"],
)
async def test_an_item_that_does_not_fit_is_an_input_error_and_changes_nothing(
    couples: Couples, db: PostgresDatabase, action: CareAction, item: str
) -> None:
    couple = await couples.create(updated_at=T0)

    with pytest.raises(InvalidItemError):
        await bruno_cares(db, couple, action, item=item)

    assert await needs_seen_by_bruno(db, couple) == dict.fromkeys(Need, 80)


async def test_feeding_without_an_item_is_an_input_error(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    command = ApplyCareAction(
        actor=couple.actor(couple.bruno),
        pet_id=couple.pet_of_alice.id,
        action=CareAction.FEED,
        idempotency_key="no-item",
    )

    with pytest.raises(InvalidItemError):
        await apply_care_action(command, db=db, clock=FixedClock(T0))


async def test_a_retry_returns_the_reaction_seen_the_first_time(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(updated_at=T0)
    await rate(couples, couple, couple.pet_of_alice.id, "paella", Affinity.LOVES)
    first = await bruno_cares(db, couple, CareAction.FEED, key="tap", item="paella")
    # Alice changes her mind between the tap and its retry.
    await rate(couples, couple, couple.pet_of_alice.id, "paella", Affinity.HATES)

    retried = await bruno_cares(db, couple, CareAction.FEED, key="tap", item="paella")

    assert retried.reaction == first.reaction
    assert retried.reaction == Reaction(item=ItemKey.PAELLA, affinity=Affinity.LOVES)
    assert retried.deltas == first.deltas


async def test_a_key_reused_for_another_item_is_refused(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(needs_of_alices_pet={Need.HUNGER: 20}, updated_at=T0)
    await bruno_cares(db, couple, CareAction.FEED, key="reused", item="pizza")

    with pytest.raises(IdempotencyKeyReusedError):
        await bruno_cares(db, couple, CareAction.FEED, key="reused", item="sushi")

    assert (await needs_seen_by_bruno(db, couple))[Need.HUNGER] == 50


async def test_falling_sick_is_noted_and_a_retry_returns_it(
    couples: Couples, db: PostgresDatabase
) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 19), updated_at=T0
    )

    first = await bruno_cares(db, couple, CareAction.FEED, key="sick-tap")
    retried = await bruno_cares(db, couple, CareAction.FEED, key="sick-tap")

    assert first.sickness is SicknessChange.FELL_SICK
    assert retried.sickness is SicknessChange.FELL_SICK


async def test_healing_is_noted(couples: Couples, db: PostgresDatabase) -> None:
    couple = await couples.create(
        needs_of_alices_pet=dict.fromkeys(Need, 40) | {Need.HYGIENE: 0},
        updated_at=T0,
    )
    await couples.admin.execute(
        "update app.pets set sick_since = $2 where id = $1",
        couple.pet_of_alice.id,
        T0 - timedelta(hours=5),
    )

    healed = await bruno_cares(db, couple, CareAction.BATHE)
    then = await bruno_cares(db, couple, CareAction.PET)

    assert healed.sickness is SicknessChange.HEALED
    assert then.sickness is None
    assert healed.reaction is None


@pytest.mark.parametrize("affinity", ["7", "true"])
async def test_a_stored_reaction_out_of_range_is_a_schema_drift_not_a_crash(
    couples: Couples, db: PostgresDatabase, affinity: str
) -> None:
    couple = await couples.create(updated_at=T0)
    await couples.admin.execute(
        "insert into app.pet_events (couple_id, pet_id, actor_user_id, source, action,"
        " payload, rules_version, idempotency_key) "
        "values ($1, $2, $3, 'ui', 'feed', $4::jsonb, 'test', 'drifted')",
        couple.id,
        couple.pet_of_alice.id,
        couple.bruno,
        f'{{"effective": true, "item_key": "pizza", "affinity": {affinity}}}',
    )

    with pytest.raises(UnexpectedPayloadError):
        await bruno_cares(db, couple, CareAction.FEED, key="drifted", item="pizza")

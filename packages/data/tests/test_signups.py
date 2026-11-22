"""Signups from the allowlist (ADR 0007): the hook that gates them and the births.

Supabase Auth runs both as supabase_auth_admin: the hook when someone signs up and the
trigger when it inserts the user. These tests do the same in SQL against local Supabase.
"""

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import ADMIN_URL, API_URL, Couples

from twochi_application.actors import UserActor
from twochi_application.home import get_home
from twochi_application.testing import FixedClock
from twochi_data.database import PostgresDatabase
from twochi_data.sql import Row, connect, text_at
from twochi_domain.care import RULES_VERSION
from twochi_domain.ids import CoupleId, UserId
from twochi_domain.pet import BIRTH_NEED_VALUE

pytestmark = pytest.mark.anyio

# Local Supabase's superuser (fixed local credentials): only it may become
# supabase_auth_admin, the role whose grants are under test.
SUPERUSER_URL = ADMIN_URL.replace("postgres:postgres@", "supabase_admin:postgres@", 1)


@dataclass(frozen=True, slots=True)
class Listed:
    """A couple given signups: two allowlisted emails, none signed up yet."""

    couple_id: CoupleId
    alice: str
    bruno: str


async def allow_couple(couples: Couples) -> Listed:
    couple = CoupleId(uuid4())
    tag = uuid4().hex
    alice, bruno = f"alice-{tag}@twochi.test", f"bruno-{tag}@twochi.test"
    await couples.admin.execute("insert into app.couples (id) values ($1)", couple)
    await couples.admin.execute(
        "insert into app.signup_allowlist "
        "(email, couple_id, display_name, pet_name, pet_model_key) values "
        "($1, $3, 'Alice', 'Ali', 'model-alice'), "
        "($2, $3, 'Bruno', 'Bru', 'model-bruno')",
        alice,
        bruno,
        couple,
    )
    return Listed(couple, alice, bruno)


async def run_as_auth(query: str, *args: object) -> list[Row]:
    connection = await connect(SUPERUSER_URL)
    try:
        async with connection.transaction():
            await connection.execute("set local role supabase_auth_admin")
            return await connection.fetch(query, *args)
    finally:
        await connection.close()


async def before_user_created(email: str | None) -> object:
    event = {
        "metadata": {"name": "before-user-created"},
        "user": {"id": str(uuid4()), "email": email, "aud": "authenticated"},
    }
    rows = await run_as_auth(
        "select app.before_user_created_hook($1::jsonb)::text as result",
        json.dumps(event),
    )
    return json.loads(text_at(rows[0], "result"))


async def sign_up(email: str) -> UserId:
    """What Supabase Auth does once the hook lets someone in: insert the user."""
    user = UserId(uuid4())
    await run_as_auth(
        "insert into auth.users (id, email, aud, role) "
        "values ($1, $2, 'authenticated', 'authenticated')",
        user,
        email,
    )
    return user


@pytest.fixture
async def db() -> AsyncIterator[PostgresDatabase]:
    database = PostgresDatabase(API_URL, require_tls=False)
    try:
        yield database
    finally:
        await database.close()


def actor(user: UserId, couple: CoupleId) -> UserActor:
    claims: Mapping[str, object] = {
        "sub": str(user),
        "role": "authenticated",
        "aal": "aal2",
        "couple_id": str(couple),
    }
    return UserActor(user_id=user, claims=claims)


async def test_the_hook_accepts_an_allowlisted_email_in_any_case(
    couples: Couples,
) -> None:
    listed = await allow_couple(couples)

    assert await before_user_created(listed.alice.upper()) == {}


@pytest.mark.parametrize("email", ["stranger@twochi.test", None])
async def test_the_hook_rejects_anyone_off_the_list(email: str | None) -> None:
    result = await before_user_created(email)

    assert result == {"error": {"http_code": 403, "message": "Signups are closed."}}


async def test_the_first_signup_creates_a_profile_and_no_pet(couples: Couples) -> None:
    listed = await allow_couple(couples)

    alice = await sign_up(listed.alice)

    profiles = await couples.admin.fetch(
        "select couple_id, display_name from app.profiles where user_id = $1", alice
    )
    pets = await couples.admin.fetch(
        "select id from app.pets where couple_id = $1", listed.couple_id
    )
    assert [(p["couple_id"], p["display_name"]) for p in profiles] == [
        (listed.couple_id, "Alice")
    ]
    assert pets == []


async def test_the_second_signup_gives_birth_to_both_pets(couples: Couples) -> None:
    listed = await allow_couple(couples)

    alice = await sign_up(listed.alice)
    bruno = await sign_up(listed.bruno)

    pets = await couples.admin.fetch(
        "select id, represents_user_id, caretaker_user_id, name, model_key, asleep, "
        "sick_since from app.pets where couple_id = $1 order by name",
        listed.couple_id,
    )
    assert [
        (
            p["represents_user_id"],
            p["caretaker_user_id"],
            p["name"],
            p["model_key"],
            p["asleep"],
            p["sick_since"],
        )
        for p in pets
    ] == [
        (alice, bruno, "Ali", "model-alice", False, None),
        (bruno, alice, "Bru", "model-bruno", False, None),
    ]
    for pet in pets:
        needs = await couples.admin.fetch(
            "select need, value from app.pet_needs where pet_id = $1", pet["id"]
        )
        assert {n["need"]: n["value"] for n in needs} == dict.fromkeys(
            ["hunger", "energy", "hygiene", "fun", "affection"], BIRTH_NEED_VALUE
        )
        events = await couples.admin.fetch(
            "select couple_id, actor_user_id, source, action, rules_version "
            "from app.pet_events where pet_id = $1",
            pet["id"],
        )
        assert [
            tuple(e[c] for c in ("couple_id", "actor_user_id", "source"))
            for e in events
        ] == [(listed.couple_id, None, "system")]
        assert [(e["action"], e["rules_version"]) for e in events] == [
            ("birth", RULES_VERSION)
        ]


async def test_after_both_signups_each_person_is_home_with_the_pet_they_care_for(
    couples: Couples, db: PostgresDatabase
) -> None:
    listed = await allow_couple(couples)
    alice = await sign_up(listed.alice)
    bruno = await sign_up(listed.bruno)
    clock = FixedClock(datetime.now(UTC))

    alices_home = await get_home(actor(alice, listed.couple_id), db=db, clock=clock)
    brunos_home = await get_home(actor(bruno, listed.couple_id), db=db, clock=clock)

    assert alices_home.pet is not None
    assert brunos_home.pet is not None
    assert alices_home.pet.pet.name == "Bru"
    assert brunos_home.pet.pet.name == "Ali"
    assert alices_home.pet.pet.id != brunos_home.pet.pet.id


async def test_a_signup_off_the_list_creates_nothing(couples: Couples) -> None:
    stranger = await sign_up(f"{uuid4().hex}@twochi.test")

    profiles = await couples.admin.fetch(
        "select 1 from app.profiles where user_id = $1", stranger
    )
    assert profiles == []


async def test_no_client_reads_the_allowlist(couples: Couples) -> None:
    listed = await allow_couple(couples)
    connection = await connect(ADMIN_URL)
    try:
        async with connection.transaction():
            await connection.execute("set local role authenticated")
            await connection.execute(
                "select set_config('request.jwt.claims', $1, true)",
                json.dumps(dict(actor(UserId(uuid4()), listed.couple_id).claims)),
            )
            with pytest.raises(Exception, match="permission denied"):
                await connection.fetch("select email from app.signup_allowlist")
    finally:
        await connection.close()

"""Fixtures shared by every test that needs the local Supabase database.

Use-case, data and API tests run against real local Postgres with RLS (Arquitectura y
convenciones, «Tests»). Each test creates its own couple and never cleans tables, so the
couple that isolates people also isolates tests and lets them run in parallel.
"""

import json
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import pytest

from twochi_application.actors import UserActor
from twochi_data.sql import CONNECT_ERRORS, Connection, connect
from twochi_domain.ids import CoupleId, PetId, UserId
from twochi_domain.needs import Need

# Local Supabase (`just up`); the ports are Twochi's own, see supabase/config.toml.
ADMIN_URL = os.environ.get(
    "TWOCHI_TEST_ADMIN_URL", "postgresql://postgres:postgres@127.0.0.1:55322/postgres"
)
API_URL = os.environ.get(
    "TWOCHI_TEST_DATABASE_URL",
    "postgresql://twochi_api:twochi-api-local@127.0.0.1:55322/postgres",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass(frozen=True, slots=True)
class TestPet:
    id: PetId
    name: str


@dataclass(frozen=True, slots=True)
class TestCouple:
    """Two people and two pets: each pet represents one; the other cares for it."""

    __test__ = False  # Not a test class, despite the name pytest collects by.

    id: CoupleId
    alice: UserId
    bruno: UserId
    pet_of_alice: TestPet  # represents Alice, cared for by Bruno
    pet_of_bruno: TestPet  # represents Bruno, cared for by Alice

    def actor(self, user: UserId, *, aal: str = "aal2") -> UserActor:
        """The claims Supabase would put in this person's token."""
        claims: Mapping[str, object] = {
            "sub": str(user),
            "role": "authenticated",
            "aal": aal,
            "couple_id": str(self.id),
        }
        return UserActor(user_id=user, claims=claims)


@dataclass(frozen=True, slots=True)
class Couples:
    """Creates couples straight in the database, as the admin, bypassing the API."""

    admin: Connection

    async def create(
        self,
        *,
        needs_of_alices_pet: Mapping[Need, float] | None = None,
        updated_at: datetime | None = None,
        with_pets: bool = True,
    ) -> TestCouple:
        couple = CoupleId(uuid4())
        alice, bruno = UserId(uuid4()), UserId(uuid4())
        pet_a, pet_b = PetId(uuid4()), PetId(uuid4())
        # One statement, one round trip: foreign keys are checked at its end, so the
        # order of the CTEs does not matter.
        await self.admin.execute(
            _CREATE_COUPLE,
            couple,
            alice,
            bruno,
            pet_a,
            pet_b,
            with_pets,
            json.dumps({n.value: v for n, v in (needs_of_alices_pet or {}).items()}),
            updated_at,
        )
        return TestCouple(
            id=couple,
            alice=alice,
            bruno=bruno,
            pet_of_alice=TestPet(pet_a, "Ali"),
            pet_of_bruno=TestPet(pet_b, "Bru"),
        )


# $1 couple, $2 Alice, $3 Bruno, $4 Alice's pet (Bruno cares), $5 Bruno's pet (Alice
# cares), $6 with pets, $7 needs of Alice's pet as JSON (80 if absent), $8 updated_at.
_CREATE_COUPLE = """
with
  users as (
    insert into auth.users (id, email, aud, role)
    select id, id::text || '@twochi.test', 'authenticated', 'authenticated'
    from unnest(array[$2::uuid, $3::uuid]) as id
  ),
  couple as (insert into app.couples (id) values ($1::uuid)),
  profiles as (
    insert into app.profiles (user_id, couple_id, display_name)
    values ($2::uuid, $1::uuid, 'Alice'), ($3::uuid, $1::uuid, 'Bruno')
  ),
  pets as (
    insert into app.pets
      (id, couple_id, represents_user_id, caretaker_user_id, name, model_key)
    select * from (values
      ($4::uuid, $1::uuid, $2::uuid, $3::uuid, 'Ali', 'placeholder'),
      ($5::uuid, $1::uuid, $3::uuid, $2::uuid, 'Bru', 'placeholder')
    ) as pet
    where $6::boolean
  )
insert into app.pet_needs (pet_id, couple_id, need, value, updated_at)
select pet, $1::uuid, need,
       coalesce(case when pet = $4::uuid then ($7::jsonb ->> need)::float8 end, 80),
       coalesce($8::timestamptz, now())
from unnest(array[$4::uuid, $5::uuid]) as pet
cross join unnest(array['hunger', 'energy', 'hygiene', 'fun', 'affection']) as need
where $6::boolean
"""


@pytest.fixture
async def couples() -> AsyncIterator[Couples]:
    try:
        admin = await connect(ADMIN_URL)
    except CONNECT_ERRORS as error:
        pytest.fail(
            f"Local Supabase is not reachable ({error}); start it with `just up`."
        )
    try:
        yield Couples(admin)
    finally:
        await admin.close()

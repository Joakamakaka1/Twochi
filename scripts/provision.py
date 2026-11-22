"""`just provision`: who may sign up, and the test couple (ADR 0007).

Reads a local TOML file that git ignores (`supabase/provision.example.toml` shows its
shape). It writes the couples and the signup allowlist, then creates the test couple's
users through the Auth admin API: the smoke user, with a password and a verified TOTP,
and a partner without a password. The signup trigger does the rest: profiles and pets.

Running it again changes nothing already in place. It never prints an email, a name or
a secret, only counts; the smoke user's credentials go to a file git ignores. Against
production it needs `--production`, and the AI runs it only with the user's explicit OK.
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx2

from twochi_data.sql import Connection, connect, text_at, uuid_at

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "supabase" / "provision.toml"
DEFAULT_OUT = ROOT / "supabase" / ".provision"

# ASCII only: Python's and Postgres' lower() agree on it, and so does the table's check.
EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
MODEL_KEY = re.compile(r"[a-z0-9_-]{1,40}")


class ProvisionError(Exception):
    """The file, the target or Auth refused the run. Messages never name a person."""


@dataclass(frozen=True, slots=True)
class Person:
    """Someone who may sign up, and the pet that will represent them."""

    email: str
    display_name: str = field(repr=False)
    pet_name: str = field(repr=False)
    pet_model_key: str


@dataclass(frozen=True, slots=True)
class CoupleEntry:
    timezone: str
    people: tuple[Person, Person]
    # How its people sign up: the real couples with Google only.
    provider: str = "google"


@dataclass(frozen=True, slots=True)
class SmokeCouple:
    """The test couple: the smoke user signs in; the partner never does."""

    timezone: str
    smoke: Person
    partner: Person

    @property
    def couple(self) -> CoupleEntry:
        # Created through the admin API with email; nobody signs up as them.
        return CoupleEntry(self.timezone, (self.smoke, self.partner), provider="email")


@dataclass(frozen=True, slots=True)
class Plan:
    couples: tuple[CoupleEntry, ...]
    test_couple: SmokeCouple | None


# --- The file -------------------------------------------------------------------------


def load_plan(text: str) -> Plan:
    """Validate the file. Errors say where, never what: the values are personal."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        # The decoder reports a position, never the offending value.
        raise ProvisionError(f"The file is not valid TOML: {error}.") from None
    # The file is the whole list: a misspelt table would read as no couple at all and
    # empty the allowlist. Unknown keys are refused at every level.
    _only(data, {"couples", "test_couple"}, "The file")
    couples = tuple(
        _couple(_table(raw, f"couples[{i}]"), f"couples[{i}]")
        for i, raw in enumerate(_list(data.get("couples", []), "couples"))
    )
    test_couple = None
    if (raw := data.get("test_couple")) is not None:
        table = _table(raw, "test_couple")
        _only(table, {"timezone", "smoke", "partner"}, "test_couple")
        test_couple = SmokeCouple(
            timezone=_timezone(table, "test_couple"),
            smoke=_person(table.get("smoke"), "test_couple.smoke"),
            partner=_person(table.get("partner"), "test_couple.partner"),
        )
    if not couples:
        raise ProvisionError("The file lists no couple; it would empty the allowlist.")
    everyone = [p for c in couples for p in c.people]
    if test_couple is not None:
        everyone += test_couple.couple.people
    if len({p.email for p in everyone}) != len(everyone):
        raise ProvisionError("An email appears more than once in the file.")
    return Plan(couples, test_couple)


def _couple(table: Mapping[str, object], where: str) -> CoupleEntry:
    _only(table, {"timezone", "people"}, where)
    people = _list(table.get("people"), f"{where}.people")
    if len(people) != 2:
        raise ProvisionError(f"{where} must have exactly two people.")
    first, second = (_person(p, f"{where}.people[{i}]") for i, p in enumerate(people))
    return CoupleEntry(_timezone(table, where), (first, second))


def _person(raw: object, where: str) -> Person:
    table = _table(raw, where)
    _only(table, {"email", "display_name", "pet_name", "pet_model_key"}, where)
    email = _text(table, "email", where, max_length=320).lower()
    if not EMAIL.fullmatch(email):
        raise ProvisionError(f"{where}.email is not an email address.")
    model_key = _text(table, "pet_model_key", where, max_length=40)
    if not MODEL_KEY.fullmatch(model_key):
        raise ProvisionError(f"{where}.pet_model_key must match [a-z0-9_-]{{1,40}}.")
    return Person(
        email=email,
        display_name=_text(table, "display_name", where, max_length=60),
        pet_name=_text(table, "pet_name", where, max_length=40),
        pet_model_key=model_key,
    )


def _timezone(table: Mapping[str, object], where: str) -> str:
    if "timezone" not in table:
        return "Europe/Madrid"
    return _text(table, "timezone", where, max_length=64)


def _only(table: Mapping[str, object], allowed: set[str], where: str) -> None:
    if unknown := sorted(set(table) - allowed):
        raise ProvisionError(f"{where} has unknown keys: {', '.join(unknown)}.")


def _table(raw: object, where: str) -> Mapping[str, object]:
    if not isinstance(raw, dict):
        raise ProvisionError(f"{where} must be a table.")
    return cast(Mapping[str, object], raw)


def _list(raw: object, where: str) -> Sequence[object]:
    if not isinstance(raw, list):
        raise ProvisionError(f"{where} must be an array of tables.")
    return cast(Sequence[object], raw)


def _text(table: Mapping[str, object], key: str, where: str, *, max_length: int) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= max_length:
        raise ProvisionError(
            f"{where}.{key} must be text of 1 to {max_length} characters."
        )
    return value.strip()


# --- TOTP (RFC 6238) ------------------------------------------------------------------


def totp(secret: str, *, at: float, digits: int = 6, step: int = 30) -> str:
    """The code of a base32 `secret` at the Unix time `at`, as authenticator apps do."""
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", int(at // step)), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    (number,) = struct.unpack(">I", mac[offset : offset + 4])
    return str((number & 0x7FFFFFFF) % 10**digits).zfill(digits)


# --- Where it runs --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    db_url: str = field(repr=False)
    api_url: str
    secret_key: str = field(repr=False)
    require_tls: bool


def local_target() -> Target:
    """Local Supabase, from `supabase status` (it must be running: `just up`)."""
    supabase = shutil.which("supabase")
    if supabase is None:
        raise ProvisionError("The Supabase CLI is not on PATH.")
    status = subprocess.run(  # noqa: S603 - fixed arguments, CLI resolved on PATH
        [supabase, "status", "-o", "env"],
        capture_output=True,
        text=True,
        check=False,
    )
    values = dict(_env_lines(status.stdout))
    try:
        return Target(
            name="local",
            db_url=values["DB_URL"],
            api_url=values["API_URL"],
            secret_key=values.get("SECRET_KEY") or values["SERVICE_ROLE_KEY"],
            require_tls=False,
        )
    except KeyError:
        raise ProvisionError(
            "Local Supabase is not running; start it with `just up`."
        ) from None


def production_target(env: Mapping[str, str]) -> Target:
    """The hosted project, from variables the user sets without echoing them."""
    names = ("TWOCHI_PROVISION_DB_URL", "SUPABASE_URL", "SUPABASE_SECRET_KEY")
    if missing := [n for n in names if not env.get(n)]:
        raise ProvisionError(f"--production needs {', '.join(missing)}.")
    if not env["SUPABASE_URL"].startswith("https://"):
        raise ProvisionError(
            "SUPABASE_URL must be https: the secret key travels on it."
        )
    return Target(
        name="production",
        db_url=env["TWOCHI_PROVISION_DB_URL"],
        api_url=env["SUPABASE_URL"].rstrip("/"),
        secret_key=env["SUPABASE_SECRET_KEY"],
        require_tls=True,
    )


def _env_lines(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            pairs.append((key.strip(), value.strip().strip('"')))
    return pairs


# --- The run --------------------------------------------------------------------------


@dataclass(slots=True)
class Report:
    couples_created: int = 0
    rows_written: int = 0
    rows_removed: int = 0
    users_created: int = 0
    totp_enrolled: bool = False
    smoke_rotated: bool = False

    def __str__(self) -> str:
        return (
            f"{self.couples_created} couples created, "
            f"{self.rows_written} allowlist rows written, "
            f"{self.rows_removed} removed, {self.users_created} users created, "
            f"smoke TOTP {'enrolled' if self.totp_enrolled else 'unchanged'}"
            + (", smoke credentials rotated" if self.smoke_rotated else "")
        )


async def provision(
    plan: Plan, target: Target, *, out_dir: Path, rotate_smoke: bool = False
) -> Report:
    report = Report()
    couples = [*plan.couples]
    if plan.test_couple is not None:
        couples.append(plan.test_couple.couple)
    connection = await connect(target.db_url, require_tls=target.require_tls)
    try:
        # The allowlist commits before any user is created: the hook and the signup
        # trigger read it when Auth inserts the test couple.
        async with connection.transaction():
            for couple in couples:
                await _allow_couple(connection, couple, report)
            # The file is the whole list: whoever left it may no longer sign up. A
            # profile already created stays; the list only gates new signups.
            status = await connection.execute(
                "delete from app.signup_allowlist where email <> all($1)",
                [p.email for c in couples for p in c.people],
            )
            report.rows_removed += _affected(status)
            # A person listed in one couple and now written into another lands in the
            # couple of whoever was already listed: refuse rather than pile them up.
            uneven = await connection.fetch(
                "select 1 from app.signup_allowlist "
                "group by couple_id having count(*) <> 2"
            )
            if uneven:
                raise ProvisionError(
                    "A couple would end with other than two people on the list. Take "
                    "whoever changed couples out of the file, run provision, then add "
                    "them back."
                )
        if plan.test_couple is not None:
            async with httpx2.AsyncClient(
                base_url=f"{target.api_url}/auth/v1",
                headers={
                    "apikey": target.secret_key,
                    "Authorization": f"Bearer {target.secret_key}",
                },
                timeout=20,
            ) as auth:
                await _create_test_couple(
                    connection,
                    auth,
                    plan.test_couple,
                    report,
                    out_dir / f"{target.name}.smoke.env",
                    rotate=rotate_smoke,
                )
    finally:
        await connection.close()
    return report


async def _allow_couple(
    connection: Connection, couple: CoupleEntry, report: Report
) -> None:
    known = await connection.fetch(
        "select 1 from pg_timezone_names where name = $1", couple.timezone
    )
    if not known:
        raise ProvisionError("A couple's timezone is not a known time zone.")
    emails = [p.email for p in couple.people]
    rows = await connection.fetch(
        "select distinct couple_id from app.signup_allowlist where email = any($1)",
        emails,
    )
    if len(rows) > 1:
        raise ProvisionError("The two people of a couple are listed in two couples.")
    if rows:
        couple_id = uuid_at(rows[0], "couple_id")
        await connection.execute(
            "update app.couples set timezone = $2 where id = $1 and timezone <> $2",
            couple_id,
            couple.timezone,
        )
    else:
        created = await connection.fetch(
            "insert into app.couples (timezone) values ($1) returning id",
            couple.timezone,
        )
        couple_id = uuid_at(created[0], "id")
        report.couples_created += 1
    for person in couple.people:
        status = await connection.execute(
            _UPSERT_ROW, *_row(person, couple_id), couple.provider
        )
        report.rows_written += _affected(status)


_UPSERT_ROW = """
insert into app.signup_allowlist
  (email, couple_id, display_name, pet_name, pet_model_key, provider)
values ($1, $2, $3, $4, $5, $6)
on conflict (email) do update set
  display_name = excluded.display_name,
  pet_name = excluded.pet_name,
  pet_model_key = excluded.pet_model_key,
  provider = excluded.provider
where (signup_allowlist.display_name, signup_allowlist.pet_name,
       signup_allowlist.pet_model_key, signup_allowlist.provider)
  is distinct from (excluded.display_name, excluded.pet_name, excluded.pet_model_key,
                    excluded.provider)
"""


def _row(person: Person, couple_id: UUID) -> tuple[object, ...]:
    return (
        person.email,
        couple_id,
        person.display_name,
        person.pet_name,
        person.pet_model_key,
    )


def _affected(status: str) -> int:
    """Rows a command touched, from its tag: `INSERT 0 1`, `DELETE 2`."""
    return int(status.rsplit(" ", 1)[-1])


async def _create_test_couple(
    connection: Connection,
    auth: httpx2.AsyncClient,
    couple: SmokeCouple,
    report: Report,
    credentials_file: Path,
    *,
    rotate: bool,
) -> None:
    # The partner first: the allowlist already names both, and every user Auth creates
    # shortens the time someone else could try to sign up as them.
    if await _find_user(connection, couple.partner.email) is None:
        await _create_user(auth, couple.partner.email, None)
        report.users_created += 1

    credentials = _read_credentials(credentials_file)
    smoke = await _find_user(connection, couple.smoke.email)
    if smoke is None:
        password = secrets.token_urlsafe(32)
        smoke = await _create_user(auth, couple.smoke.email, password)
        report.users_created += 1
        # Saved before enrolling: a run cut short can still sign in and finish.
        credentials = {"SMOKE_EMAIL": couple.smoke.email, "SMOKE_PASSWORD": password}
        _write_credentials(credentials_file, credentials)
    elif rotate:
        # The user keeps its id, profile and pet: deleting it is blocked once its pet
        # exists, and a new user would never see another birth.
        password = secrets.token_urlsafe(32)
        await _call(
            auth,
            "PUT",
            f"/admin/users/{smoke}",
            "setting a new password",
            json={"password": password},
        )
        await _remove_totp_factors(connection, auth, smoke, verified_too=True)
        credentials = {"SMOKE_EMAIL": couple.smoke.email, "SMOKE_PASSWORD": password}
        _write_credentials(credentials_file, credentials)
        report.smoke_rotated = True
    elif credentials.get("SMOKE_EMAIL") != couple.smoke.email:
        raise ProvisionError(
            f"The smoke user exists, but {credentials_file.name} does not hold its "
            "password. Run `just provision --rotate-smoke` to give it new ones."
        )

    if not await _has_verified_totp(connection, smoke, auth):
        secret = await _enroll_totp(auth, couple.smoke.email, credentials)
        credentials = {**credentials, "SMOKE_TOTP_SECRET": secret}
        _write_credentials(credentials_file, credentials)
        report.totp_enrolled = True
    elif "SMOKE_TOTP_SECRET" not in credentials:
        raise ProvisionError(
            f"The smoke user has a TOTP factor, but {credentials_file.name} does not "
            "hold its secret. Run `just provision --rotate-smoke` to enroll a new one."
        )


async def _find_user(connection: Connection, email: str) -> UUID | None:
    rows = await connection.fetch(
        "select id from auth.users where lower(email) = $1", email
    )
    return uuid_at(rows[0], "id") if rows else None


async def _create_user(
    auth: httpx2.AsyncClient, email: str, password: str | None
) -> UUID:
    body: dict[str, object] = {"email": email, "email_confirm": True}
    if password is not None:
        body["password"] = password
    user = await _call(auth, "POST", "/admin/users", "creating a user", json=body)
    return UUID(_text_field(user, "id"))


async def _has_verified_totp(
    connection: Connection, user: UUID, auth: httpx2.AsyncClient
) -> bool:
    if await _totp_factors(connection, user, verified=True):
        return True
    # Leftovers of an enrolment cut short: Auth refuses a second unverified factor.
    await _remove_totp_factors(connection, auth, user, verified_too=False)
    return False


async def _totp_factors(
    connection: Connection, user: UUID, *, verified: bool | None
) -> list[UUID]:
    rows = await connection.fetch(
        "select id, status::text as status from auth.mfa_factors "
        "where user_id = $1 and factor_type = 'totp'",
        user,
    )
    return [
        uuid_at(r, "id")
        for r in rows
        if verified is None or (text_at(r, "status") == "verified") == verified
    ]


async def _remove_totp_factors(
    connection: Connection, auth: httpx2.AsyncClient, user: UUID, *, verified_too: bool
) -> None:
    for factor in await _totp_factors(
        connection, user, verified=None if verified_too else False
    ):
        await _call(
            auth,
            "DELETE",
            f"/admin/users/{user}/factors/{factor}",
            "removing a TOTP factor",
        )


async def _enroll_totp(
    auth: httpx2.AsyncClient, email: str, credentials: Mapping[str, str]
) -> str:
    """Enroll and verify a TOTP factor as the smoke user would in the app."""
    session = await _call(
        auth,
        "POST",
        "/token?grant_type=password",
        "signing the smoke user in",
        json={"email": email, "password": credentials["SMOKE_PASSWORD"]},
    )
    as_smoke = {"Authorization": f"Bearer {_text_field(session, 'access_token')}"}
    factor = await _call(
        auth,
        "POST",
        "/factors",
        "enrolling TOTP",
        json={"factor_type": "totp", "friendly_name": "smoke"},
        headers=as_smoke,
    )
    factor_id = _text_field(factor, "id")
    totp_fields = factor.get("totp")
    if not isinstance(totp_fields, dict):
        raise ProvisionError("Auth enrolled TOTP without returning its secret.")
    secret = _text_field(cast(Mapping[str, object], totp_fields), "secret")
    challenge = await _call(
        auth,
        "POST",
        f"/factors/{factor_id}/challenge",
        "challenging TOTP",
        headers=as_smoke,
    )
    await _call(
        auth,
        "POST",
        f"/factors/{factor_id}/verify",
        "verifying TOTP",
        json={
            "challenge_id": _text_field(challenge, "id"),
            "code": totp(secret, at=time.time()),
        },
        headers=as_smoke,
    )
    return secret


async def _call(
    auth: httpx2.AsyncClient,
    method: str,
    path: str,
    doing: str,
    *,
    json: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    response = await auth.request(method, path, json=json, headers=headers)
    if response.is_error:
        # Auth's error code names the problem (`email_exists`) without echoing input.
        code = _error_code(response)
        raise ProvisionError(
            f"Auth refused {doing}: HTTP {response.status_code}{code}."
        )
    if not response.content:
        return {}
    body: object = response.json()
    return cast(Mapping[str, object], body) if isinstance(body, dict) else {}


def _error_code(response: httpx2.Response) -> str:
    try:
        body: object = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        code = cast(Mapping[str, object], body).get("error_code")
        if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code):
            return f" ({code})"
    return ""


def _text_field(body: Mapping[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise ProvisionError(f"Auth answered without `{key}`.")
    return value


def _read_credentials(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(_env_lines(path.read_text(encoding="utf-8")))


def _write_credentials(path: Path, credentials: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(f'{key}="{value}"\n' for key, value in credentials.items())
    # Created owner-only from the start (on POSIX), never readable for a moment.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)


# --- Command line ---------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision", description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--rotate-smoke",
        action="store_true",
        help="Give the existing smoke user a new password and TOTP, when its "
        "credentials file is lost.",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Write to the hosted project, from TWOCHI_PROVISION_DB_URL, SUPABASE_URL "
        "and SUPABASE_SECRET_KEY. Only with the user's explicit OK.",
    )
    args = parser.parse_args(argv)
    file = cast(Path, args.file)
    try:
        if not file.exists():
            raise ProvisionError(
                f"{file} is missing: copy supabase/provision.example.toml there."
            )
        plan = load_plan(file.read_text(encoding="utf-8"))
        target = production_target(os.environ) if args.production else local_target()
        report = asyncio.run(
            provision(
                plan,
                target,
                out_dir=cast(Path, args.out),
                rotate_smoke=cast(bool, args.rotate_smoke),
            ),
            # The selector loop: Windows' default proactor raises on reset sockets.
            loop_factory=asyncio.SelectorEventLoop,
        )
    except ProvisionError as error:
        sys.stderr.write(f"provision: {error}\n")
        return 1
    except Exception as error:
        # Postgres and Auth errors can quote the failing row: name only the error.
        code = getattr(error, "sqlstate", None)
        detail = f" (SQLSTATE {code})" if isinstance(code, str) else ""
        sys.stderr.write(
            f"provision: failed with {type(error).__name__}{detail}; its message is "
            "withheld because it may name a person.\n"
        )
        return 2
    sys.stdout.write(f"provision {target.name}: {report}.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

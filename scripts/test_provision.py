"""`just provision`: the file it reads, the TOTP it computes, and a real run.

The run goes against local Supabase (`just up`): Postgres for the allowlist and Auth for
the test couple's users, as `provision` does against production. A run makes the
allowlist match its file, so it clears what other tests left there: these tests must
not run at the same time as the signup tests.
"""

import asyncio
import base64
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from conftest import ADMIN_URL
from provision import ProvisionError, load_plan, local_target, main, totp

from twochi_data.sql import connect

EXAMPLE = Path(__file__).parent.parent / "supabase" / "provision.example.toml"

PERSON = """
email = "{email}"
display_name = "Alice"
pet_name = "Ali"
pet_model_key = "placeholder"
"""


def couple_toml(*emails: str) -> str:
    people = "".join(
        "\n[[couples.people]]" + PERSON.format(email=email) for email in emails
    )
    return '[[couples]]\ntimezone = "Europe/Madrid"\n' + people


def test_the_example_file_is_a_valid_plan() -> None:
    plan = load_plan(EXAMPLE.read_text(encoding="utf-8"))

    assert len(plan.couples) == 1
    assert plan.test_couple is not None


def test_emails_are_kept_in_lower_case() -> None:
    plan = load_plan(couple_toml("Alice@Twochi.TEST", "bruno@twochi.test"))

    assert [p.email for p in plan.couples[0].people] == [
        "alice@twochi.test",
        "bruno@twochi.test",
    ]


@pytest.mark.parametrize(
    "toml",
    [
        couple_toml("secret-alice@twochi.test"),
        couple_toml("secret-alice@twochi.test", "x@t.es", "y@t.es"),
        couple_toml("secret-alice@twochi.test", "secret-alice@twochi.test"),
        couple_toml("secret-alice@twochi.test", "not-an-email"),
        couple_toml("secret-alice@twochi.test", "josé@twochi.test"),
        couple_toml("secret-alice@twochi.test", "b@t.es").replace(
            '"placeholder"', '"Bad Key"', 1
        ),
        couple_toml("secret-alice@twochi.test", "b@t.es").replace('"Alice"', '""', 1),
        "[[couples]]\nthis is not toml",
    ],
    ids=[
        "one-person",
        "three-people",
        "repeated-email",
        "bad-email",
        "non-ascii-email",
        "bad-model-key",
        "empty-name",
        "not-toml",
    ],
)
def test_a_wrong_file_is_refused_without_naming_anyone(toml: str) -> None:
    with pytest.raises(ProvisionError) as refused:
        load_plan(toml)

    assert "secret-alice" not in str(refused.value)
    assert "Alice" not in str(refused.value)


# RFC 6238, appendix B: the SHA-1 secret "12345678901234567890", eight digits.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("at", "code"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1234567890, "89005924"),
        (20000000000, "65353130"),
    ],
)
def test_totp_matches_the_rfc_vectors(at: int, code: str) -> None:
    assert totp(RFC_SECRET, at=at, digits=8) == code


# --- A real run against local Supabase ----------------------------------------------


def fresh_plan_toml() -> str:
    tag = uuid4().hex
    return f"""
[[couples]]
timezone = "Europe/Madrid"

[[couples.people]]
email = "real-a-{tag}@twochi.test"
display_name = "Nombre-A-{tag}"
pet_name = "Pet-A"
pet_model_key = "placeholder"

[[couples.people]]
email = "real-b-{tag}@twochi.test"
display_name = "Nombre-B-{tag}"
pet_name = "Pet-B"
pet_model_key = "placeholder"

[test_couple]
[test_couple.smoke]
email = "smoke-{tag}@twochi.test"
display_name = "Humo-{tag}"
pet_name = "Humito"
pet_model_key = "placeholder"

[test_couple.partner]
email = "partner-{tag}@twochi.test"
display_name = "Pareja-{tag}"
pet_name = "Parejita"
pet_model_key = "placeholder"
"""


async def fetch(query: str, *args: object) -> list[dict[str, object]]:
    connection = await connect(ADMIN_URL)
    try:
        return [
            {key: row[key] for key in ("value",)}
            for row in await connection.fetch(query, *args)
        ]
    finally:
        await connection.close()


def scalar(query: str, *args: object) -> object:
    rows = asyncio.run(fetch(query, *args), loop_factory=asyncio.SelectorEventLoop)
    return rows[0]["value"]


def sign_in_with_totp(credentials: dict[str, str]) -> dict[str, object]:
    """What `just smoke` will do: password, then the TOTP challenge, to reach aal2."""
    target = local_target()
    with httpx2.Client(
        base_url=f"{target.api_url}/auth/v1", headers={"apikey": target.secret_key}
    ) as auth:
        session = auth.post(
            "/token?grant_type=password",
            json={
                "email": credentials["SMOKE_EMAIL"],
                "password": credentials["SMOKE_PASSWORD"],
            },
        ).json()
        as_smoke = {"Authorization": f"Bearer {session['access_token']}"}
        factors = auth.get("/user", headers=as_smoke).json()["factors"]
        factor_id = factors[0]["id"]
        challenge = auth.post(
            f"/factors/{factor_id}/challenge", headers=as_smoke
        ).json()
        verified = auth.post(
            f"/factors/{factor_id}/verify",
            json={
                "challenge_id": challenge["id"],
                "code": totp(credentials["SMOKE_TOTP_SECRET"], at=time.time()),
            },
            headers=as_smoke,
        ).json()
    payload = verified["access_token"].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_provision_twice_writes_once_and_leaves_a_smoke_user_with_aal2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    toml = fresh_plan_toml()
    file = tmp_path / "provision.toml"
    file.write_text(toml, encoding="utf-8")
    args = ["--file", str(file), "--out", str(tmp_path / "out")]
    plan = load_plan(toml)

    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first.startswith(
        "provision local: 2 couples created, 4 allowlist rows written, "
    )
    assert first.endswith(" removed, 2 users created, smoke TOTP enrolled.\n")
    assert second == (
        "provision local: 0 couples created, 0 allowlist rows written, 0 removed, "
        "0 users created, smoke TOTP unchanged.\n"
    )
    people = [p for c in plan.couples for p in c.people]
    assert plan.test_couple is not None
    people += plan.test_couple.couple.people
    for person in people:
        assert person.email not in first + second
        assert person.display_name not in first + second
    emails = [p.email for p in people]
    assert (
        scalar(
            "select count(*) as value from app.signup_allowlist where email = any($1)",
            emails,
        )
        == 4
    )
    # The trigger gave the test couple its profiles and both pets.
    assert (
        scalar(
            "select count(*) as value from app.pets p "
            "join app.signup_allowlist a on a.couple_id = p.couple_id "
            "where a.email = $1",
            plan.test_couple.smoke.email,
        )
        == 2
    )
    assert sign_in_with_totp(credentials_at(tmp_path / "out"))["aal"] == "aal2"


def credentials_at(out: Path) -> dict[str, str]:
    text = (out / "local.smoke.env").read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in text.replace('"', "").splitlines())


def test_a_couple_taken_out_of_the_file_leaves_the_allowlist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    toml = fresh_plan_toml()
    file = tmp_path / "provision.toml"
    file.write_text(toml, encoding="utf-8")
    args = ["--file", str(file), "--out", str(tmp_path / "out")]
    plan = load_plan(toml)
    assert main(args) == 0
    capsys.readouterr()

    file.write_text(toml.split("[test_couple]", 1)[0], encoding="utf-8")
    assert main(args) == 0

    assert plan.test_couple is not None
    assert capsys.readouterr().out == (
        "provision local: 0 couples created, 0 allowlist rows written, 2 removed, "
        "0 users created, smoke TOTP unchanged.\n"
    )
    smoke_emails = [p.email for p in plan.test_couple.couple.people]
    assert (
        scalar(
            "select count(*) as value from app.signup_allowlist where email = any($1)",
            smoke_emails,
        )
        == 0
    )


def test_a_lost_credentials_file_is_recovered_only_by_rotating(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "provision.toml"
    file.write_text(fresh_plan_toml(), encoding="utf-8")
    out = tmp_path / "out"
    args = ["--file", str(file), "--out", str(out)]
    assert main(args) == 0
    first_password = credentials_at(out)["SMOKE_PASSWORD"]
    (out / "local.smoke.env").unlink()
    capsys.readouterr()

    assert main(args) == 1
    assert "--rotate-smoke" in capsys.readouterr().err
    assert main([*args, "--rotate-smoke"]) == 0

    assert capsys.readouterr().out.endswith(
        "smoke TOTP enrolled, smoke credentials rotated.\n"
    )
    credentials = credentials_at(out)
    assert credentials["SMOKE_PASSWORD"] != first_password
    assert sign_in_with_totp(credentials)["aal"] == "aal2"


def test_an_unknown_timezone_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file = tmp_path / "provision.toml"
    file.write_text(
        fresh_plan_toml().replace("Europe/Madrid", "Mars/Olympus", 1), encoding="utf-8"
    )

    assert main(["--file", str(file), "--out", str(tmp_path / "out")]) == 1
    assert "timezone" in capsys.readouterr().err

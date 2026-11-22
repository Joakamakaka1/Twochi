from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from db_dump import (
    DumpError,
    Outcome,
    check_guard,
    definer_problems,
    dump_key,
    main,
    put_dump,
    read_settings,
)

BUCKET = "twochi-backups-123456789012"


@dataclass
class FakeS3:
    """`aws s3api put-object` against a bucket that applies twochi-backup's policy.

    `enforced=False` plays a bucket where IAM never evaluated the condition keys.
    """

    enforced: bool = True
    objects: dict[str, bytes] = field(default_factory=dict[str, bytes])

    def __call__(self, args: Sequence[str]) -> Outcome:
        assert list(args[:3]) == ["aws", "s3api", "put-object"]
        flags = dict(zip(args[3::2], args[4::2], strict=True))
        assert flags["--bucket"] == BUCKET
        key = flags["--key"]
        body = Path(flags["--body"]).read_bytes() if "--body" in flags else b""
        guarded = flags.get("--if-none-match") == "*"
        if self.enforced and (not guarded or "--sse-customer-algorithm" in flags):
            return self.error("AccessDenied")
        if guarded and key in self.objects:
            return self.error("PreconditionFailed")
        self.objects[key] = body
        return Outcome(0, "")

    @staticmethod
    def error(code: str) -> Outcome:
        return Outcome(
            254, f"\nAn error occurred ({code}) when calling the PutObject ..."
        )


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "dump.tar.gz"
    path.write_bytes(b"dump bytes")
    return path


def test_key_has_kind_utc_time_run_and_unguessable_token() -> None:
    now = datetime(2026, 11, 22, 3, 15, 7, tzinfo=UTC)

    key = dump_key("daily", now, run_id="1234567890", token="9f" * 16)

    assert key == f"daily/20261122T031507Z-run1234567890-{'9f' * 16}.tar.gz"


def test_uploads_the_dump_under_its_new_key(archive: Path) -> None:
    s3 = FakeS3()

    put_dump(s3, BUCKET, "daily/a.tar.gz", archive)

    assert s3.objects == {"daily/a.tar.gz": b"dump bytes"}


def test_a_key_that_already_exists_fails_and_keeps_the_old_dump(archive: Path) -> None:
    s3 = FakeS3(objects={"daily/a.tar.gz": b"older"})

    with pytest.raises(DumpError, match="412"):
        put_dump(s3, BUCKET, "daily/a.tar.gz", archive)

    assert s3.objects == {"daily/a.tar.gz": b"older"}


def probe_keys() -> Callable[[], str]:
    numbers = iter(range(1, 100))
    return lambda: f"probes/{next(numbers)}"


def test_the_guard_holds_when_the_bucket_enforces_the_policy(archive: Path) -> None:
    s3 = FakeS3()
    put_dump(s3, BUCKET, "daily/a.tar.gz", archive)

    problems = check_guard(s3, BUCKET, "daily/a.tar.gz", archive, probe_keys())

    assert problems == []
    assert s3.objects == {"daily/a.tar.gz": b"dump bytes"}


def test_the_guard_fails_when_iam_ignores_the_condition_keys(archive: Path) -> None:
    s3 = FakeS3(enforced=False)
    put_dump(s3, BUCKET, "daily/a.tar.gz", archive)

    problems = check_guard(s3, BUCKET, "daily/a.tar.gz", archive, probe_keys())

    assert len(problems) == 2
    assert "If-None-Match" in problems[0]
    assert "SSE-C" in problems[1]


ENV = {
    "BACKUPS_BUCKET": BUCKET,
    "SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co",
    "SUPABASE_POOLER_HOST": "aws-1-eu-west-1.pooler.supabase.com",
    "BACKUP_DB_PASSWORD": "s3cret-value",
    "GITHUB_RUN_ID": "1234567890",
}


def test_settings_log_in_as_the_backup_role_of_the_project() -> None:
    settings = read_settings(ENV)

    assert settings.db_user == "twochi_backup.abcdefghijklmnopqrst"
    assert settings.pooler_host == "aws-1-eu-west-1.pooler.supabase.com"
    assert "s3cret-value" not in repr(settings)


def test_a_missing_or_blank_value_fails_and_names_it() -> None:
    env = {**ENV, "BACKUP_DB_PASSWORD": "", "SUPABASE_POOLER_HOST": " "}
    del env["BACKUPS_BUCKET"]

    with pytest.raises(DumpError) as error:
        read_settings(env)

    assert "BACKUPS_BUCKET, SUPABASE_POOLER_HOST, BACKUP_DB_PASSWORD" in str(
        error.value
    )


def test_a_url_that_is_not_a_supabase_project_fails() -> None:
    with pytest.raises(DumpError, match="SUPABASE_URL"):
        read_settings({**ENV, "SUPABASE_URL": "https://example.com"})


def test_a_function_that_runs_with_its_owners_rights_is_a_problem() -> None:
    listing = "public.add_points(integer)\nextensions.grant_pg_net_access()\n"

    problems = definer_problems(listing)

    assert len(problems) == 2
    assert "public.add_points(integer)" in problems[0]


def test_no_such_function_is_no_problem() -> None:
    assert definer_problems("\n") == []


def test_an_unknown_kind_is_a_usage_error() -> None:
    assert main(["db_dump.py", "weekly"]) == 2


def test_missing_settings_end_red_before_any_dump(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    assert main(["db_dump.py", "daily"]) == 1
    assert "::error title=database dump::Missing" in capsys.readouterr().out


def test_a_failed_upload_keeps_the_cli_message(archive: Path) -> None:
    def no_credentials(args: Sequence[str]) -> Outcome:
        return Outcome(253, "\nUnable to locate credentials. You can configure ...\n")

    with pytest.raises(DumpError, match="Unable to locate credentials"):
        put_dump(no_credentials, BUCKET, "daily/a.tar.gz", archive)


def test_a_listing_that_could_not_run_is_a_problem() -> None:
    problems = definer_problems(None)

    assert len(problems) == 1
    assert "could not" in problems[0]

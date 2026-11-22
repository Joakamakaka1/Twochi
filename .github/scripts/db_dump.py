"""Dump the production database and upload it to the backups bucket (ADR 0011, 0012).

pg_dump 17 runs in a pinned postgres image, as the read-only `twochi_backup` role,
through Supavisor in session mode (IPv4, like GitHub's runners) and with TLS checked
against Supabase's root. Roles, schema and data go into one archive, uploaded with a
single create-only PUT; then the bucket's guard is probed. The log keeps the key, time,
size and SHA-256 that a restore must match.

Usage:
  python db_dump.py KIND    KIND is `daily` or `pre-deploy`
"""

import hashlib
import os
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KINDS = ("daily", "pre-deploy")
# pg_dump must not be older than the server (Postgres 17). Pinned by digest; to update,
# `docker buildx imagetools inspect postgres:<tag>` and copy the index digest.
DUMP_IMAGE = (
    "postgres:17.12-trixie"
    "@sha256:223efeb196329b55b3b9a13db144956411dbc18e727e59f681c3e0aede6475cf"
)
DUMP_SCRIPT = Path(__file__).with_name("supabase_dump.sh")
# The root that signs the pooler (ADR 0010); libpq checks the chain and the host name.
SUPABASE_CA = ROOT / "packages/data/src/twochi_data/supabase-root-2021-ca.pem"
DUMP_FILES = ("roles.sql", "schema.sql", "data.sql")
# Written by supabase_dump.sh, never packed: what twochi_backup may run as its owner.
DEFINERS_FILE = "definer_functions.txt"


class DumpError(Exception):
    """The dump never reached the bucket, or the bucket's guard is not ADR 0011's."""


@dataclass(frozen=True, slots=True)
class Outcome:
    returncode: int
    stderr: str


# The AWS CLI behind a seam, so the tests can play a bucket with IAM's policy.
type Run = Callable[[Sequence[str]], Outcome]

_ERROR_CODE = re.compile(r"An error occurred \((\w+)\)")


_PROJECT_URL = re.compile(r"https://([a-z0-9]{20})\.supabase\.co/?")
_REQUIRED = (
    "BACKUPS_BUCKET",
    "SUPABASE_URL",
    "SUPABASE_POOLER_HOST",
    "BACKUP_DB_PASSWORD",
    "GITHUB_RUN_ID",
)


@dataclass(frozen=True, slots=True)
class Settings:
    bucket: str
    pooler_host: str
    db_user: str
    db_password: str = field(repr=False)
    run_id: str


def read_settings(env: Mapping[str, str]) -> Settings:
    """What the job needs; a missing value fails the job instead of skipping it."""
    values = {name: env.get(name, "").strip() for name in _REQUIRED}
    if missing := [name for name, value in values.items() if not value]:
        raise DumpError(
            f"Missing in the backup environment: {', '.join(missing)}. "
            "No dump was made."
        )
    project = _PROJECT_URL.fullmatch(values["SUPABASE_URL"])
    if project is None:
        raise DumpError("SUPABASE_URL is not https://<ref>.supabase.co.")
    return Settings(
        bucket=values["BACKUPS_BUCKET"],
        pooler_host=values["SUPABASE_POOLER_HOST"],
        # Supavisor tells projects apart by the user's suffix.
        db_user=f"twochi_backup.{project.group(1)}",
        db_password=values["BACKUP_DB_PASSWORD"],
        run_id=values["GITHUB_RUN_ID"],
    )


@dataclass(frozen=True, slots=True)
class _Failure:
    code: str  # the S3 error code, or `unknown` when the CLI failed before S3 answered
    # The CLI's last stderr line: what the code alone cannot say. An AccessDenied names
    # the account ID and the bucket; the job masks both (`mask-aws-account-id` and the
    # BACKUPS_BUCKET secret), so keep those masks if this ever moves.
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _put(
    run: Run, bucket: str, key: str, *options: str, body: Path | None = None
) -> _Failure | None:
    args = ["aws", "s3api", "put-object", "--bucket", bucket, "--key", key, *options]
    if body is not None:
        args += ["--body", str(body)]
    outcome = run(args)
    if outcome.returncode == 0:
        return None
    # The AWS CLI only says which S3 error it got in its stderr.
    match = _ERROR_CODE.search(outcome.stderr)
    lines = [line.strip() for line in outcome.stderr.splitlines() if line.strip()]
    return _Failure(
        match.group(1) if match else "unknown",
        lines[-1] if lines else f"exit code {outcome.returncode}",
    )


def put_dump(run: Run, bucket: str, key: str, archive: Path) -> None:
    """One PUT from a file, refused if the key exists: never multipart, never over."""
    error = _put(run, bucket, key, "--if-none-match", "*", body=archive)
    if error is not None and error.code == "PreconditionFailed":
        raise DumpError(
            f"412: {key} already existed. Its random part makes that impossible by "
            "chance: someone created it in advance. The dump was not uploaded."
        )
    if error is not None:
        raise DumpError(f"The upload of {key} failed with {error}.")


def check_guard(
    run: Run, bucket: str, key: str, archive: Path, fresh_key: Callable[[], str]
) -> list[str]:
    """Prove on the real bucket what IAM's policy simulator cannot (ADR 0011).

    Returns what does not hold; empty when all does. Each probe would be denied as the
    policy intends, so none leaves an object behind unless the guard is broken.
    """
    problems: list[str] = []
    # The same bytes again: if the guard were broken, the dump would stay as it was.
    replay = _put(run, bucket, key, "--if-none-match", "*", body=archive)
    if replay is None or replay.code != "PreconditionFailed":
        problems.append(f"Repeating {key} gave {replay or 'success'}, not 412.")
    bare = fresh_key()
    if (error := _put(run, bucket, bare)) is None or error.code != "AccessDenied":
        problems.append(
            f"An upload without If-None-Match to {bare} gave {error or 'success'}, "
            "not 403: the role could overwrite dumps."
        )
    sse_c = fresh_key()
    customer_key = secrets.token_hex(16)  # 32 bytes, thrown away
    sse_c_options = ("--if-none-match", "*", "--sse-customer-algorithm", "AES256")
    error = _put(run, bucket, sse_c, *sse_c_options, "--sse-customer-key", customer_key)
    if error is None or error.code != "AccessDenied":
        problems.append(
            f"An SSE-C upload to {sse_c} gave {error or 'success'}, not 403: a dump "
            "could be encrypted with a key nobody keeps."
        )
    return problems


def dump_key(kind: str, now: datetime, *, run_id: str, token: str) -> str:
    """A new key per dump: UTC time, the run that made it and a part nobody can guess.

    With keys by time alone, a compromised job on `main` could create tomorrow's keys
    in advance, and every real dump would then fail with 412.
    """
    return f"{kind}/{now:%Y%m%dT%H%M%SZ}-run{run_id}-{token}.tar.gz"


def definer_problems(listing: str | None) -> list[str]:
    """Each SECURITY DEFINER function twochi_backup may run, as a problem (ADR 0012).

    pg_read_all_data opens every schema, so such a function, from an extension enabled
    in the dashboard for instance, would let the role write as the function's owner.
    The local test sees only the migrations; this sees production. `None` means the
    listing could not run: the dump is already up, so that is a problem, not a failure.
    """
    if listing is None:
        return ["The SECURITY DEFINER functions could not be listed: see psql above."]
    return [
        f"twochi_backup may run {line}, a SECURITY DEFINER function, and could write "
        "through it. Revoke EXECUTE from PUBLIC on it; if a supabase_* role owns it, "
        "only Supabase can."
        for line in (raw.strip() for raw in listing.splitlines())
        if line
    ]


def dump_database(settings: Settings, out: Path) -> None:
    """Write roles.sql, schema.sql and data.sql into `out`.

    The password reaches the container by name (`-e PGPASSWORD`), never in an argument,
    and the TLS mode is set here, not in anything a secret holds.
    """
    pg = {
        "PGHOST": settings.pooler_host,
        "PGPORT": "5432",  # Supavisor's session mode: pg_dump needs a whole session.
        "PGDATABASE": "postgres",
        "PGUSER": settings.db_user,
        "PGPASSWORD": settings.db_password,
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": "/ca/root.pem",
        "PGAPPNAME": "twochi-backup",
    }
    args = ["docker", "run", "--rm"]
    for name in pg:
        args += ["-e", name]
    args += [
        "-v", f"{SUPABASE_CA}:/ca/root.pem:ro",
        "-v", f"{DUMP_SCRIPT}:/dump.sh:ro",
        "-v", f"{out}:/out",
        DUMP_IMAGE, "bash", "/dump.sh",
    ]  # fmt: skip
    result = subprocess.run(args, env=os.environ | pg, check=False)  # noqa: S603
    if result.returncode != 0:
        raise DumpError(f"pg_dump failed with exit code {result.returncode}.")
    for name in DUMP_FILES:
        if not (out / name).is_file() or (out / name).stat().st_size == 0:
            raise DumpError(f"The dump left {name} empty or missing.")


def pack(out: Path) -> Path:
    archive = out / "dump.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in DUMP_FILES:
            tar.add(out / name, arcname=name)
    return archive


def _run(args: Sequence[str]) -> Outcome:
    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
    return Outcome(result.returncode, result.stderr)


def _record(key: str, archive: Path, now: datetime) -> str:
    """What a restore compares against: a later key alone proves nothing."""
    with archive.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return (
        f"Dump uploaded: key {key}, {now:%Y-%m-%dT%H:%M:%SZ}, "
        f"{archive.stat().st_size} bytes, SHA-256 {digest}."
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in KINDS:
        sys.stderr.write(__doc__ or "")
        return 2
    kind = argv[1]
    try:
        settings = read_settings(os.environ)
        runner_temp = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
        with tempfile.TemporaryDirectory(dir=runner_temp) as work:
            out = Path(work)
            dump_database(settings, out)
            archive = pack(out)
            now = datetime.now(UTC)
            token = secrets.token_hex(16)
            key = dump_key(kind, now, run_id=settings.run_id, token=token)
            put_dump(_run, settings.bucket, key, archive)
            record = _record(key, archive, now)
            sys.stdout.write(f"{record}\n")
            if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
                with Path(summary).open("a", encoding="utf-8") as file:
                    file.write(f"### Database dump\n\n{record}\n")

            def probe_key() -> str:
                return dump_key(
                    "probes",
                    datetime.now(UTC),
                    run_id=settings.run_id,
                    token=secrets.token_hex(16),
                )

            problems = check_guard(_run, settings.bucket, key, archive, probe_key)
            definers = out / DEFINERS_FILE
            listing = definers.read_text("utf-8") if definers.is_file() else None
            problems += definer_problems(listing)
    except DumpError as error:
        sys.stdout.write(f"::error title=database dump::{error}\n")
        return 1
    for problem in problems:
        sys.stdout.write(f"::error title=backup guard::{problem}\n")
    if not problems:
        sys.stdout.write(
            "Guard holds: repeat 412, no If-None-Match 403, SSE-C 403. "
            "twochi_backup runs no SECURITY DEFINER function.\n"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

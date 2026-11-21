"""Build the arm64 zip of a Lambda app and name it by what goes into it.

CI/CD e IaC, «Qué se despliega según lo que cambia»: the key is the hash of `uv.lock`,
this script, `.python-version` and the source of the workspace packages the app
installs, not of the zip, so the same code never triggers a deploy. Wheels are
`aarch64` cp314 from the lockfile, with their hashes checked; workspace packages go
to the root of the zip next to `run.sh`, which keeps its execute bit.

Usage:
  python lambda_package.py key APP          print the artifacts bucket key
  python lambda_package.py build APP OUT    build OUT/<name>.zip and print its path
"""

import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = "aarch64-manylinux2014"
# Zip entries get a fixed date, so a rebuild of the same code gives the same bytes.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
EXECUTABLE = 0o100755
REGULAR = 0o100644
# Console scripts point at the build machine's Python; the handler never uses them.
SKIPPED_PARTS = frozenset({"bin", "__pycache__"})


def workspace_members(export: str) -> list[str]:
    """Return the workspace directories in `uv export --no-editable` output, sorted."""
    return sorted(
        line.removeprefix("./").strip()
        for line in export.splitlines()
        if line.startswith("./")
    )


def is_packaged_source(path: str) -> bool:
    """Tell whether a tracked file of a workspace package can change the zip."""
    return "tests" not in PurePosixPath(path).parts


def package_key(app: str, inputs: Mapping[str, bytes]) -> str:
    """Return the bucket key for these inputs, keyed by path; order does not matter."""
    digest = hashlib.sha256()
    for path in sorted(inputs):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(inputs[path]).hexdigest().encode())
        digest.update(b"\n")
    return f"{app}/{digest.hexdigest()}.zip"


def write_zip(source: Path, out: Path, *, executables: Iterable[str] = ()) -> None:
    """Zip a directory tree with fixed dates and modes; `executables` keep 0755."""
    executable = set(executables)
    files = sorted(
        path
        for path in source.rglob("*")
        if path.is_file()
        and not SKIPPED_PARTS.intersection(path.relative_to(source).parts)
    )
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            name = path.relative_to(source).as_posix()
            entry = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            entry.external_attr = (EXECUTABLE if name in executable else REGULAR) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())


def _run(*args: str) -> str:
    return subprocess.run(  # noqa: S603 — fixed tools, arguments built here
        args, cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def _export(app: str, *extra: str) -> str:
    return _run(
        "uv", "export", "--package", f"twochi-{app}", "--frozen", "--no-dev",
        "--no-editable", "--no-header", *extra,
    )  # fmt: skip


def _python_version() -> str:
    """Major and minor from `.python-version`, which the Lambda runtime matches."""
    full = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    return ".".join(full.split(".")[:2])


def key(app: str) -> str:
    """Compute the key of an app from the files in the working tree."""
    members = workspace_members(_export(app, "--no-hashes"))
    tracked = _run("git", "ls-files", "-z", "--", *members).split("\0")
    sources = [path for path in tracked if path and is_packaged_source(path)]
    script = Path(__file__).resolve().relative_to(ROOT).as_posix()
    paths = ["uv.lock", ".python-version", script, *sources]
    return package_key(app, {path: (ROOT / path).read_bytes() for path in paths})


def build(app: str, out_dir: Path) -> Path:
    """Install the app for Lambda arm64 into a temporary tree and zip it."""
    members = workspace_members(_export(app, "--no-hashes"))
    install = (
        "uv", "pip", "install", "--no-installer-metadata", "--no-compile-bytecode",
        "--python-platform", PLATFORM, "--python-version", _python_version(),
    )  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "package"
        requirements = Path(tmp) / "requirements.txt"
        requirements.write_text(_export(app, "--no-emit-workspace"), encoding="utf-8")
        # Third-party: wheels only, each checked against the hash in uv.lock.
        _run(
            *install, "--only-binary", ":all:", "--require-hashes",
            "--target", str(target), "-r", str(requirements),
        )  # fmt: skip
        # Workspace packages: built from this checkout, dependencies already in place.
        local = [f"./{member}" for member in members]
        _run(*install, "--no-deps", "--target", str(target), *local)
        handler = ROOT / "apps" / app / "run.sh"
        if handler.is_file():
            shutil.copyfile(handler, target / handler.name)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / PurePosixPath(key(app)).name
        write_zip(target, out, executables=["run.sh"])
    return out


def main(argv: list[str]) -> int:
    match argv[1:]:
        case ["key", app]:
            sys.stdout.write(f"{key(app)}\n")
        case ["build", app, out]:
            sys.stdout.write(f"{build(app, Path(out))}\n")
        case _:
            sys.stderr.write("usage: lambda_package.py key APP | build APP OUT\n")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

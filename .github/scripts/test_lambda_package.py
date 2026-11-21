import zipfile
from pathlib import Path

from lambda_package import is_packaged_source, package_key, workspace_members, write_zip

EXPORT = """\
./apps/api
./packages/domain
annotated-types==0.8.0
    # via pydantic
fastapi==0.162.7
"""


def test_workspace_members_come_from_local_lines_only() -> None:
    assert workspace_members(EXPORT) == ["apps/api", "packages/domain"]


def test_tests_never_change_the_package() -> None:
    assert is_packaged_source("packages/domain/src/twochi_domain/needs.py")
    assert is_packaged_source("apps/api/run.sh")
    assert not is_packaged_source("packages/domain/tests/test_needs.py")


def test_key_ignores_input_order() -> None:
    first = package_key("api", {"uv.lock": b"a", "apps/api/run.sh": b"b"})
    second = package_key("api", {"apps/api/run.sh": b"b", "uv.lock": b"a"})
    assert first == second
    assert first.startswith("api/")
    assert first.endswith(".zip")


def test_key_changes_with_content_or_path() -> None:
    base = package_key("api", {"uv.lock": b"a"})
    assert package_key("api", {"uv.lock": b"b"}) != base
    assert package_key("api", {"uv.lock2": b"a"}) != base
    assert package_key("worker", {"uv.lock": b"a"}) != base


def make_tree(root: Path) -> None:
    (root / "twochi_api").mkdir(parents=True)
    (root / "twochi_api" / "main.py").write_text("app = 1\n", encoding="utf-8")
    (root / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "bin").mkdir()
    (root / "bin" / "uvicorn").write_text("#!/usr/bin/python\n", encoding="utf-8")
    (root / "twochi_api" / "__pycache__").mkdir()
    (root / "twochi_api" / "__pycache__" / "main.pyc").write_bytes(b"\0")


def test_zip_keeps_run_sh_executable_and_skips_build_leftovers(tmp_path: Path) -> None:
    make_tree(tmp_path / "tree")
    out = tmp_path / "api.zip"
    write_zip(tmp_path / "tree", out, executables=["run.sh"])
    with zipfile.ZipFile(out) as archive:
        modes = {
            entry.filename: entry.external_attr >> 16 for entry in archive.infolist()
        }
    assert modes == {"run.sh": 0o100755, "twochi_api/main.py": 0o100644}


def test_zip_is_reproducible(tmp_path: Path) -> None:
    make_tree(tmp_path / "tree")
    write_zip(tmp_path / "tree", tmp_path / "a.zip", executables=["run.sh"])
    write_zip(tmp_path / "tree", tmp_path / "b.zip", executables=["run.sh"])
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()

import json
from pathlib import Path

import pytest
from project_ref_guard import main

REF = "qwertyuiopasdfghjklz"
ORG = "mnbvcxzlkjhgfdsapoiu"
SLUG = "plokijuhygtfrdeswaqz"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """What `supabase link` leaves in supabase/.temp."""
    folder = tmp_path / ".temp"
    folder.mkdir()
    project = {
        "ref": REF,
        "name": "twochi",
        "organization_id": ORG,
        "organization_slug": SLUG,
    }
    (folder / "linked-project.json").write_text(json.dumps(project), encoding="utf-8")
    return folder


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run(temp_dir: Path, *files: Path) -> int:
    return main(["project_ref_guard.py", *map(str, files)], temp_dirs=[temp_dir])


def test_a_file_with_the_linked_ref_is_refused_without_printing_it(
    tmp_path: Path, temp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    leaked = write(tmp_path, "test_leak.py", f'URL = "https://{REF}.supabase.co"\n')
    clean = write(tmp_path, "test_clean.py", 'URL = "https://example.supabase.co"\n')

    status = run(temp_dir, leaked, clean)

    output = capsys.readouterr()
    assert status == 1
    assert str(leaked) in output.err
    assert str(clean) not in output.err
    assert REF not in output.out + output.err


@pytest.mark.parametrize("private", [ORG, SLUG])
def test_the_organization_ids_are_refused_too(
    tmp_path: Path, temp_dir: Path, private: str
) -> None:
    leaked = write(tmp_path, "notes.md", f"org {private}\n")

    assert run(temp_dir, leaked) == 1


def test_files_without_them_pass(tmp_path: Path, temp_dir: Path) -> None:
    clean = write(tmp_path, "test_clean.py", "the project is called twochi\n")

    assert run(temp_dir, clean) == 0


def test_a_ref_file_alone_still_guards(tmp_path: Path) -> None:
    # Other CLI versions write only `project-ref`.
    folder = tmp_path / ".temp"
    folder.mkdir()
    (folder / "project-ref").write_text(f"{REF}\n", encoding="utf-8")
    leaked = write(tmp_path, "test_leak.py", f"{REF}\n")

    assert run(folder, leaked) == 1


def test_a_broken_linked_project_fails_with_a_clear_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / ".temp"
    folder.mkdir()
    (folder / "linked-project.json").write_text('{"ref": "trunc', encoding="utf-8")
    anything = write(tmp_path, "test_any.py", "x\n")

    assert run(folder, anything) == 1
    assert "supabase link" in capsys.readouterr().err


def test_without_a_linked_project_there_is_nothing_to_compare(tmp_path: Path) -> None:
    anything = write(tmp_path, "test_any.py", f"{REF}\n")

    assert run(tmp_path / "none", anything) == 0


def test_a_worktree_falls_back_to_the_main_checkout(
    tmp_path: Path, temp_dir: Path
) -> None:
    # A worktree has no gitignored files: its own supabase/.temp does not exist.
    leaked = write(tmp_path, "test_leak.py", f"{REF}\n")

    status = main(
        ["project_ref_guard.py", str(leaked)],
        temp_dirs=[tmp_path / "worktree" / ".temp", temp_dir],
    )

    assert status == 1


def test_a_utf16_file_is_refused(tmp_path: Path, temp_dir: Path) -> None:
    # What Windows PowerShell 5.1 writes when output is redirected to a file.
    leaked = tmp_path / "projects.txt"
    leaked.write_bytes(f"\ufeff{REF}\r\n".encode("utf-16-le"))

    assert run(temp_dir, leaked) == 1


def test_a_linked_project_without_known_ids_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / ".temp"
    folder.mkdir()
    renamed = {"project_ref": REF, "name": "twochi"}
    (folder / "linked-project.json").write_text(json.dumps(renamed), encoding="utf-8")
    anything = write(tmp_path, "test_any.py", "x\n")

    assert run(folder, anything) == 1
    assert "supabase link" in capsys.readouterr().err

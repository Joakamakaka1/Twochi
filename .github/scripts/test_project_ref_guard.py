import json
from pathlib import Path

import pytest
from project_ref_guard import main

REF = "qwertyuiopasdfghjklz"
ORG = "mnbvcxzlkjhgfdsapoiu"


@pytest.fixture
def linked(tmp_path: Path) -> Path:
    path = tmp_path / "linked-project.json"
    project = {
        "ref": REF,
        "name": "twochi",
        "organization_id": ORG,
        "organization_slug": "twochi-org",
    }
    path.write_text(json.dumps(project), encoding="utf-8")
    return path


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_with_the_linked_ref_is_refused_without_printing_it(
    tmp_path: Path, linked: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    leaked = write(tmp_path, "test_leak.py", f'URL = "https://{REF}.supabase.co"\n')
    clean = write(tmp_path, "test_clean.py", 'URL = "https://example.supabase.co"\n')

    status = main(["project_ref_guard.py", str(leaked), str(clean)], linked=linked)

    output = capsys.readouterr()
    assert status == 1
    assert str(leaked) in output.err
    assert str(clean) not in output.err
    assert REF not in output.out + output.err


def test_the_organization_id_is_refused_too(tmp_path: Path, linked: Path) -> None:
    leaked = write(tmp_path, "notes.md", f"org {ORG}\n")

    assert main(["project_ref_guard.py", str(leaked)], linked=linked) == 1


def test_files_without_them_pass(tmp_path: Path, linked: Path) -> None:
    clean = write(tmp_path, "test_clean.py", "the project is called twochi\n")

    assert main(["project_ref_guard.py", str(clean)], linked=linked) == 0


def test_without_a_linked_project_there_is_nothing_to_compare(tmp_path: Path) -> None:
    anything = write(tmp_path, "test_any.py", f"{REF}\n")

    status = main(["project_ref_guard.py", str(anything)], linked=tmp_path / "none")

    assert status == 0

import json
import unicodedata
from pathlib import Path

import pytest
from flujo import PullRequest, check, load, main, warnings_for

COMPLETE_BODY = (
    "## Tamaño\n\nDelicado: toca el CI.\n\n"
    "## Evidencia\n\njust check en verde.\n\n"
    "## Revisión\n\nDos subagentes, sin hallazgos altos ni medios.\n\n"
    "## Peligro de fusión\n\nDos sentidos.\n"
)
PR24_BODY = (Path(__file__).parent / "testdata" / "flujo_pr24_body.md").read_text(
    encoding="utf-8"
)
PR24_FILES = (
    ".github/scripts/check_dump.py",
    ".github/scripts/test_check_dump.py",
    ".github/workflows/ci.yml",
    "docs/adr/0012-dump-with-read-only-role.md",
    "justfile",
)
PR24_TITLE = "ci: dump and restore the local database on every Python PR (TWO-41)"


def pr(
    title: str,
    *,
    body: str = COMPLETE_BODY,
    author: str = "someone",
    changed: tuple[str, ...] = ("packages/domain/src/twochi_domain/needs.py",),
) -> PullRequest:
    return PullRequest(title=title, body=body, author=author, changed_files=changed)


def body_with(size: str, *, review: str = "Un subagente, sin hallazgos.") -> str:
    return (
        f"## Tamaño\n\n{size}\n\n## Evidencia\n\nok\n\n"
        f"## Revisión\n\n{review}\n\n## Peligro de fusión\n\nok\n"
    )


def test_accepts_conventional_title_without_id_outside_sensitive_paths() -> None:
    assert check(pr("fix(domain): clamp need values", body="")) == []


def test_accepts_conventional_title_with_id_and_breaking_mark() -> None:
    assert check(pr("feat(api)!: rename turn fields (TWO-42)")) == []


def test_rejects_title_that_is_not_conventional() -> None:
    errors = check(pr("Add CI pipeline"))
    assert len(errors) == 1
    assert "Conventional Commits" in errors[0]


def test_rejects_unknown_type() -> None:
    assert check(pr("feature(domain): add affinity bonus"))


def test_rejects_malformed_id() -> None:
    assert check(pr("feat(domain): add affinity bonus (two-42)"))


def test_sensitive_paths_require_id_and_both_sections() -> None:
    errors = check(
        pr("ci: add pipeline", body="", changed=(".github/workflows/ci.yml",))
    )
    assert len(errors) == 3


def test_sensitive_paths_pass_with_id_and_sections() -> None:
    assert (
        check(pr("ci: add pipeline (TWO-2)", changed=("infra/bootstrap/main.tf",)))
        == []
    )


def test_section_headings_are_matched_case_insensitively() -> None:
    body = (
        "# TAMAÑO\nDelicado\n### evidencia\nok\n"
        "### revisión\nok\n## PELIGRO DE FUSIÓN\nok\n"
    )
    assert check(pr("ci: add pipeline (TWO-2)", body=body, changed=("justfile",))) == []


def test_section_named_only_in_text_does_not_count() -> None:
    body = (
        "## Tamaño\n\nDelicado.\n\n## Revisión\n\nUno, limpio.\n\n"
        "Sin evidencia ni peligro de fusión por ahora."
    )
    errors = check(
        pr("ci: add pipeline (TWO-2)", body=body, changed=("CODING_STANDARDS.md",))
    )
    assert len(errors) == 2


def test_dependabot_is_exempt_from_id_and_sections() -> None:
    dependabot = pr(
        "build(deps): bump actions/checkout from 7.0.1 to 7.1.0",
        body="",
        author="dependabot[bot]",
        changed=(".github/workflows/ci.yml",),
    )
    assert check(dependabot) == []


def test_dependabot_still_needs_a_conventional_title() -> None:
    assert check(pr("Bump actions/checkout", author="dependabot[bot]", body=""))


def test_template_placeholders_do_not_count_as_content() -> None:
    body = (
        "## Tamaño\n\nDelicado.\n\n"
        "## Evidencia\n\n<!-- just check y lo que se probó a mano -->\n\n"
        "## Revisión\n\nUno, limpio.\n\n"
        "## Peligro de fusión\n\n<!-- un sentido o dos -->\n"
    )
    errors = check(pr("ci: add pipeline (TWO-2)", body=body, changed=("justfile",)))
    assert len(errors) == 2


def test_empty_section_does_not_count() -> None:
    body = body_with("Delicado.").replace("## Evidencia\n\nok", "## Evidencia")
    errors = check(pr("ci: add pipeline (TWO-2)", body=body, changed=("justfile",)))
    assert len(errors) == 1
    assert "Evidencia" in errors[0]


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "CLAUDE.md",
        "AGENTS.md",
        "apps/web/eslint.config.js",
        "apps/api/src/twochi_api/auth.py",
    ],
)
def test_files_that_weaken_checks_are_sensitive(path: str) -> None:
    assert check(pr("build: tweak config", body="", changed=(path,)))


# Size: every PR with an id declares it, and the zone decides it, not the lines.


def test_id_without_size_section_fails() -> None:
    body = COMPLETE_BODY.replace("## Tamaño\n\nDelicado: toca el CI.\n\n", "")
    errors = check(pr("feat(domain): add affinity bonus (TWO-42)", body=body))
    assert len(errors) == 1
    assert "Tamaño" in errors[0]


def test_size_section_with_only_the_template_hint_fails() -> None:
    body = body_with("<!-- trivial, normal, complejo o delicado -->")
    errors = check(pr("feat(domain): add affinity bonus (TWO-42)", body=body))
    assert len(errors) == 1
    assert "Tamaño" in errors[0]


def test_size_section_must_name_a_known_size() -> None:
    errors = check(
        pr("feat(domain): add affinity bonus (TWO-42)", body=body_with("Mediano."))
    )
    assert len(errors) == 1
    assert "trivial, normal, complejo o delicado" in errors[0]


@pytest.mark.parametrize(
    "size", ["Trivial", "normal, una rebanada", "Complejo", "DELICADO"]
)
def test_any_known_size_passes_outside_sensitive_paths(size: str) -> None:
    assert check(pr("feat(domain): add bonus (TWO-42)", body=body_with(size))) == []


def test_size_word_inside_another_word_does_not_count() -> None:
    errors = check(
        pr("feat(domain): add bonus (TWO-42)", body=body_with("Anormalmente grande."))
    )
    assert len(errors) == 1
    assert "trivial, normal, complejo o delicado" in errors[0]


@pytest.mark.parametrize("size", ["Normal: un cambio pequeño.", "trivial"])
@pytest.mark.parametrize(
    "path", ["infra/bootstrap/main.tf", ".github/workflows/ci.yml", "justfile"]
)
def test_small_size_in_a_sensitive_path_fails(size: str, path: str) -> None:
    errors = check(pr("ci: tweak (TWO-2)", body=body_with(size), changed=(path,)))
    assert len(errors) == 1
    assert "delicado" in errors[0]
    assert path in errors[0]


@pytest.mark.parametrize("size", ["Complejo", "Delicado: toca infra/."])
def test_large_size_in_a_sensitive_path_passes(size: str) -> None:
    changed = ("infra/bootstrap/main.tf",)
    assert check(pr("ci: tweak (TWO-2)", body=body_with(size), changed=changed)) == []


def test_first_size_named_is_the_declared_one() -> None:
    body = body_with("Normal, aunque roce algo delicado.")
    errors = check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",)))
    assert len(errors) == 1
    assert "delicado, not normal" in errors[0]


def test_trivial_pr_without_id_needs_no_size_or_review() -> None:
    assert check(pr("docs: fix a typo in the glossary", body="", changed=())) == []


# Review: normal, complex and sensitive PRs say who reviewed and what they found.


@pytest.mark.parametrize("size", ["Normal", "Complejo", "Delicado"])
def test_review_section_is_required_above_trivial(size: str) -> None:
    body = body_with(size).replace(
        "## Revisión\n\nUn subagente, sin hallazgos.\n\n", ""
    )
    errors = check(pr("feat(domain): add bonus (TWO-42)", body=body))
    assert len(errors) == 1
    assert "Revisión" in errors[0]


def test_review_template_hint_does_not_count() -> None:
    body = body_with("Normal", review="<!-- cuántos subagentes y qué encontraron -->")
    errors = check(pr("feat(domain): add bonus (TWO-42)", body=body))
    assert len(errors) == 1
    assert "Revisión" in errors[0]


def test_trivial_with_id_needs_no_review() -> None:
    body = "## Tamaño\n\nTrivial: una errata.\n"
    assert check(pr("docs: fix a typo (TWO-42)", body=body)) == []


def test_missing_size_still_asks_for_review() -> None:
    errors = check(pr("feat(domain): add bonus (TWO-42)", body=""))
    assert any("Tamaño" in error for error in errors)
    assert any("Revisión" in error for error in errors)


# A real body: PR 24 before and after the new sections.


def test_pr24_body_as_it_was_fails_for_missing_size_and_review() -> None:
    errors = check(pr(PR24_TITLE, body=PR24_BODY, changed=PR24_FILES))
    assert len(errors) == 2
    assert "«Tamaño»" in errors[0]
    assert "«Revisión»" in errors[1]


def test_pr24_body_with_the_new_sections_passes() -> None:
    body = PR24_BODY.replace(
        "## Qué cambia",
        "## Tamaño\n\nDelicado: cambia el CI y el `justfile`.\n\n## Qué cambia",
    ).replace(
        "## Antes y después",
        "## Revisión\n\nTres revisiones: estándares y spec (un subagente), "
        "`/code-review` xhigh y revisor de seguridad. Tres hallazgos, arreglados.\n\n"
        "## Antes y después",
    )
    assert check(pr(PR24_TITLE, body=body, changed=PR24_FILES)) == []


def test_pr24_body_declared_normal_fails_for_its_sensitive_paths() -> None:
    body = PR24_BODY.replace(
        "## Qué cambia", "## Tamaño\n\nNormal.\n\n## Revisión\n\nUno.\n\n## Qué cambia"
    )
    errors = check(pr(PR24_TITLE, body=body, changed=PR24_FILES))
    assert len(errors) == 1
    assert "justfile" in errors[0]


# Warnings: code in apps/ or packages/ without any test changed. They never fail.


@pytest.mark.parametrize(
    "path",
    [
        "apps/api/src/twochi_api/routes.py",
        "apps/web/src/features/care/CareButton.tsx",
        "packages/domain/src/twochi_domain/needs.py",
    ],
)
def test_code_without_tests_warns_but_passes(path: str) -> None:
    untested = pr("feat(domain): add bonus (TWO-42)", changed=(path,))
    assert check(untested) == []
    warnings = warnings_for(untested)
    assert len(warnings) == 1
    assert path in warnings[0]


@pytest.mark.parametrize(
    "test_path",
    [
        "packages/domain/tests/test_needs.py",
        "apps/web/src/features/care/needBars.test.ts",
        "apps/web/src/shared/api/signedFetch.spec.tsx",
        "apps/api/tests/conftest.py",
    ],
)
def test_code_with_a_test_does_not_warn(test_path: str) -> None:
    changed = ("packages/domain/src/twochi_domain/needs.py", test_path)
    assert warnings_for(pr("feat(domain): add bonus (TWO-42)", changed=changed)) == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/adr/0015-x.md",
        "apps/web/package.json",
        "apps/web/src/styles.css",
        "apps/web/vite.config.ts",
        "packages/api-client/src/schema.gen.ts",
        ".github/scripts/flujo.py",
    ],
)
def test_changes_that_are_not_app_code_do_not_warn(path: str) -> None:
    assert warnings_for(pr("chore: tidy (TWO-42)", changed=(path,))) == []


def test_dependabot_does_not_warn() -> None:
    bump = pr(
        "build(deps): bump zod",
        body="",
        author="dependabot[bot]",
        changed=("apps/web/src/shared/api/client.ts",),
    )
    assert warnings_for(bump) == []


def write_event(tmp_path: Path, *, title: str, body: str, changed: str) -> Path:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "title": title,
                    "body": body,
                    "user": {"login": "someone"},
                }
            }
        ),
        encoding="utf-8",
    )
    changed_path = tmp_path / "changed.bin"
    changed_path.write_bytes(changed.encode())
    return changed_path


def test_main_prints_the_warning_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = write_event(
        tmp_path,
        title="feat(api): add route (TWO-42)",
        body=body_with("Normal"),
        changed="apps/api/src/twochi_api/routes.py\0",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))

    assert main(["flujo.py", str(changed)]) == 0

    out = capsys.readouterr().out
    assert "::warning title=flujo::" in out
    assert "apps/api/src/twochi_api/routes.py" in out
    assert "::error" not in out


def test_main_fails_on_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = write_event(
        tmp_path, title="ci: tweak (TWO-2)", body="", changed="infra/main.tf\0"
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))

    assert main(["flujo.py", str(changed)]) == 1
    assert "::error title=flujo::" in capsys.readouterr().out


def test_load_reads_nul_separated_names(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "title": "ci: x (TWO-2)",
                    "body": None,
                    "user": {"login": "someone"},
                }
            }
        ),
        encoding="utf-8",
    )
    changed = tmp_path / "changed.bin"
    changed.write_bytes("infra/ñ.tf\0docs/a b.md\0".encode())

    loaded = load(event, changed)

    assert loaded.changed_files == ("infra/ñ.tf", "docs/a b.md")
    assert loaded.body == ""


# Review fixes: subheadings, headings that carry their content, fences, escaping.


def test_section_holding_only_subheadings_has_content() -> None:
    body = body_with("Delicado.", review="### Corrección\n\nSin hallazgos.")
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


def test_section_ends_at_a_heading_of_its_own_level() -> None:
    body = body_with("Delicado.", review="").replace(
        "## Revisión\n\n\n\n", "## Revisión\n\n## Notas\n\nTexto ajeno.\n\n"
    )
    errors = check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",)))
    assert len(errors) == 1
    assert "«Revisión»" in errors[0]


def test_subheading_of_a_higher_level_closes_the_section() -> None:
    body = "### Tamaño\n\n## Otra cosa\n\nDelicado.\n"
    errors = check(pr("docs: x (TWO-42)", body=body))
    assert any("«Tamaño» section with content" in error for error in errors)


@pytest.mark.parametrize(
    "heading", ["## Tamaño: delicado", "## Tamaño: Delicado, toca el CI"]
)
def test_size_written_in_the_heading_counts(heading: str) -> None:
    body = body_with("x").replace("## Tamaño\n\nx", heading)
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


def test_heading_with_a_trailing_colon_is_the_section() -> None:
    body = body_with("Delicado.").replace("## Tamaño\n", "## Tamaño:\n")
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


def test_section_names_without_accents_count() -> None:
    body = (
        "## Tamano\n\nDelicado.\n\n## Evidencia\n\nok\n\n"
        "## Revision\n\nUno.\n\n## Peligro de fusion\n\nok\n"
    )
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


def test_decomposed_accents_are_normalized() -> None:
    body = unicodedata.normalize("NFD", COMPLETE_BODY)
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_headings_inside_a_fenced_block_do_not_count(fence: str) -> None:
    body = (
        f"## Qué cambia\n\n{fence}md\n## Tamaño\n\nDelicado.\n\n"
        f"## Revisión\n\nUno.\n{fence}\n"
    )
    errors = check(pr("docs: x (TWO-42)", body=body))
    assert any("«Tamaño»" in error for error in errors)
    assert any("«Revisión»" in error for error in errors)


def test_a_fenced_block_is_content_of_its_section() -> None:
    body = body_with("Delicado.").replace(
        "## Evidencia\n\nok", "## Evidencia\n\n```\n32 failed\n```"
    )
    assert check(pr("ci: tweak (TWO-2)", body=body, changed=("justfile",))) == []


def test_main_escapes_workflow_commands_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = write_event(
        tmp_path,
        title="ci: tweak",  # Without an id the error names the sensitive paths.
        body="",
        changed=(
            "apps/x\n::error title=spoof::y.py\0"
            "infra/a\r\n::warning title=spoof::100%.tf\0"
        ),
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))

    assert main(["flujo.py", str(changed)]) == 1

    commands = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::")
    ]
    assert commands
    assert all(
        line.startswith(("::warning title=flujo::", "::error title=flujo::"))
        for line in commands
    )
    assert any("%0A::error title=spoof::" in line for line in commands)
    assert any("%0D%0A::warning title=spoof::100%25.tf" in line for line in commands)

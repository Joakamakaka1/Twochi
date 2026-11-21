from flujo import PullRequest, check

COMPLETE_BODY = (
    "## Evidencia\n\njust check en verde.\n\n## Peligro de fusión\n\nDos sentidos.\n"
)


def pr(
    title: str,
    *,
    body: str = COMPLETE_BODY,
    author: str = "someone",
    changed: tuple[str, ...] = ("packages/domain/src/twochi_domain/needs.py",),
) -> PullRequest:
    return PullRequest(title=title, body=body, author=author, changed_files=changed)


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
    body = "### evidencia\nok\n## PELIGRO DE FUSIÓN\nok\n"
    assert check(pr("ci: add pipeline (TWO-2)", body=body, changed=("justfile",))) == []


def test_section_named_only_in_text_does_not_count() -> None:
    body = "Sin evidencia ni peligro de fusión por ahora."
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

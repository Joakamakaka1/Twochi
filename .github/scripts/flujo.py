"""The `flujo` check: PR title, size and review, and evidence in sensitive paths.

Rules from Forma de trabajo («Cómo se fuerza el flujo»), Arquitectura y
convenciones («Git y pull requests») and CODING_STANDARDS.md («Trabajo diario»).
The PR text is read from the event file, never interpolated into a shell command.

A PR without a Linear id is trivial by definition, so it declares no size and needs
no review; in a sensitive path it already fails for the missing id. Dependabot only
needs a conventional title.

Usage: python flujo.py CHANGED_FILES  (NUL-separated; reads GITHUB_EVENT_PATH)
"""

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

TYPES = ("feat", "fix", "refactor", "perf", "test", "docs", "build", "ci", "chore")
TITLE = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9-]+\))?!?: \S.*$")
LINEAR_ID = re.compile(r"\(TWO-\d+\)$")
# Something that tries to be an id at the end of the title, in any spelling.
ID_LIKE = re.compile(r"\(\s*two[\s_-]*\d+\s*\)$", re.IGNORECASE)

# Paths whose PRs a person merges. Extend this list when a sensitive module gets its own
# path (login and aal2, privacy filter, usage caps, turn contract, memory ingest).
SENSITIVE_PREFIXES = (
    ".github/",
    ".claude/",
    "infra/",
    "supabase/",
)
# Files that can weaken a check without touching the check itself.
SENSITIVE_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "CODING_STANDARDS.md",
    "justfile",
    "mise.toml",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    "apps/web/eslint.config.js",
    # Login and aal2.
    "apps/api/src/twochi_api/auth.py",
)

REQUIRED_SECTIONS = ("Evidencia", "Peligro de fusión")
SIZE_SECTION = "Tamaño"
REVIEW_SECTION = "Revisión"
SIZES = ("trivial", "normal", "complejo", "delicado")
# The zone decides the size, not the lines: these two never fit a sensitive path.
SMALL_SIZES = ("trivial", "normal")
# The first size the section names is the declared one.
SIZE_WORD = re.compile(rf"\b(?:{'|'.join(SIZES)})\b", re.IGNORECASE)
HEADING = re.compile(r"^(#{1,3})[ \t]+(.*?)[ \t]*$", re.MULTILINE)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_PLACEHOLDER = "[code block]"
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
DEPENDABOT = "dependabot[bot]"

# Application code whose change should come with a test.
CODE_PREFIXES = ("apps/", "packages/")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


@dataclass(frozen=True, slots=True)
class PullRequest:
    title: str
    body: str
    author: str
    changed_files: tuple[str, ...]


def is_sensitive(path: str) -> bool:
    """Tell whether a changed path belongs to a sensitive zone."""
    return path in SENSITIVE_FILES or path.startswith(SENSITIVE_PREFIXES)


def is_test(path: str) -> bool:
    """Tell whether a changed path is a test, in Python or in the front."""
    name = path.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{path}"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or ".test." in name
        or ".spec." in name
    )


def is_app_code(path: str) -> bool:
    """Tell whether a path is code of an app or a package, tool configs aside."""
    name = path.rsplit("/", 1)[-1]
    return (
        path.startswith(CODE_PREFIXES)
        and name.endswith(CODE_SUFFIXES)
        and ".config." not in name
        and ".gen." not in name
        and not is_test(path)
    )


def folded(text: str) -> str:
    """Compare section names without case or accents: «Tamano» is «Tamaño»."""
    decomposed = unicodedata.normalize("NFD", text)
    bare = "".join(char for char in decomposed if not unicodedata.combining(char))
    return bare.casefold().strip()


def without_fences(body: str) -> str:
    """Swap each fenced code block for a placeholder, so its headings do not count.

    The placeholder keeps the block as content of the section that holds it.
    """
    lines: list[str] = []
    fence = ""
    for line in body.split("\n"):
        match = FENCE.match(line)
        if fence:
            # Closed by a run of the same character, at least as long, and nothing else.
            if (
                match
                and match.group(1).startswith(fence)
                and not line[match.end() :].strip()
            ):
                fence = ""
            continue
        if match:
            fence = match.group(1)
            lines.append(CODE_PLACEHOLDER)
            continue
        lines.append(line)
    return "\n".join(lines)


def section_text(body: str, name: str) -> str:
    """Return the content of the first level 1 to 3 heading with that name, or "".

    The section runs until the next heading of its level or above, so subheadings
    stay inside. Text after a colon in the heading (`## Tamaño: normal`) is content.
    Template hints are HTML comments, so an untouched template has no content.
    """
    text = without_fences(HTML_COMMENT.sub("", unicodedata.normalize("NFC", body)))
    headings = list(HEADING.finditer(text))
    for index, heading in enumerate(headings):
        title, _, inline = heading.group(2).partition(":")
        if folded(title) != folded(name):
            continue
        level = len(heading.group(1))
        end = next(
            (h.start() for h in headings[index + 1 :] if len(h.group(1)) <= level),
            len(text),
        )
        content = f"{inline}\n{text[heading.end() : end]}".strip()
        if content:
            return content
    return ""


def has_section(body: str, name: str) -> bool:
    """Tell whether a heading with that name has content of its own."""
    return bool(section_text(body, name))


def listing(paths: list[str]) -> str:
    """Name the first five paths, for an error message."""
    return ", ".join(paths[:5]) + (" …" if len(paths) > 5 else "")


def size_errors(body: str, sensitive: list[str]) -> list[str]:
    """Check the declared size against the zone, and the review it asks for."""
    errors: list[str] = []
    size_text = section_text(body, SIZE_SECTION)
    declared = SIZE_WORD.search(size_text)
    size = declared.group(0).casefold() if declared else None
    if not size_text:
        errors.append(
            f"A PR with a Linear id needs a «{SIZE_SECTION}» section with content."
        )
    elif size is None:
        errors.append(
            f"The «{SIZE_SECTION}» section must say trivial, normal, complejo o "
            "delicado."
        )
    elif size in SMALL_SIZES and sensitive:
        errors.append(
            f"Sensitive paths ({listing(sensitive)}) make the PR delicado, not {size}: "
            "the zone decides the size, not the lines."
        )
    if size != "trivial" and not has_section(body, REVIEW_SECTION):
        errors.append(
            f"Normal, complex and sensitive PRs need a «{REVIEW_SECTION}» section: "
            "how many subagents reviewed it and what they found."
        )
    return errors


def check(pr: PullRequest) -> list[str]:
    """Return the broken rules, one message each; empty when the PR passes."""
    errors: list[str] = []
    title = pr.title.strip()
    if not TITLE.match(title):
        errors.append(
            "The title must follow Conventional Commits: "
            f"type(scope): summary (TWO-n), with type one of {', '.join(TYPES)}."
        )
    elif ID_LIKE.search(title) and not LINEAR_ID.search(title):
        errors.append("The Linear id at the end of the title must read (TWO-n).")
    if pr.author == DEPENDABOT:
        return errors

    sensitive = sorted(path for path in pr.changed_files if is_sensitive(path))
    if LINEAR_ID.search(title):
        errors.extend(size_errors(pr.body, sensitive))
    if not sensitive:
        return errors
    if not LINEAR_ID.search(title):
        errors.append(
            f"Sensitive paths ({listing(sensitive)}) need the Linear id at the end of "
            "the title."
        )
    errors.extend(
        f"Sensitive paths need a «{section}» section with content in the PR body."
        for section in REQUIRED_SECTIONS
        if not has_section(pr.body, section)
    )
    return errors


def warnings_for(pr: PullRequest) -> list[str]:
    """Return what deserves a look but never fails the PR."""
    if pr.author == DEPENDABOT or any(is_test(path) for path in pr.changed_files):
        return []
    code = sorted(path for path in pr.changed_files if is_app_code(path))
    if not code:
        return []
    return [
        f"Code changed without any test ({listing(code)}): the red test goes in its "
        "own commit, before the code that passes it."
    ]


def load(event_path: Path, changed_path: Path) -> PullRequest:
    """Build the PR from the GitHub event file and the list of changed files."""
    event = cast("dict[str, Any]", json.loads(event_path.read_text(encoding="utf-8")))
    pull = cast("dict[str, Any]", event["pull_request"])
    # NUL-separated, as `git diff --name-only -z` writes it: names may hold spaces and
    # line breaks. Bytes, so a `\r` in a name is not turned into a newline.
    raw = changed_path.read_bytes().decode("utf-8")
    changed = [name for name in raw.split(chr(0)) if name]
    return PullRequest(
        title=str(pull["title"]),
        body=str(pull.get("body") or ""),
        author=str(pull["user"]["login"]),
        changed_files=tuple(changed),
    )


def escaped(message: str) -> str:
    """Escape a workflow command message as `@actions/core` does.

    A changed path may hold a newline; unescaped, it would start a command of its own.
    """
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: flujo.py CHANGED_FILES_LIST\n")
        return 2
    pr = load(Path(os.environ["GITHUB_EVENT_PATH"]), Path(argv[1]))
    for warning in warnings_for(pr):
        sys.stdout.write(f"::warning title=flujo::{escaped(warning)}\n")
    errors = check(pr)
    for error in errors:
        sys.stdout.write(f"::error title=flujo::{escaped(error)}\n")
    if not errors:
        sys.stdout.write("flujo: OK\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

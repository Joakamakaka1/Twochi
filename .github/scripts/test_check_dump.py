from pathlib import Path

from check_dump import (
    TableRows,
    exclusion_problems,
    has_own_config,
    row_differences,
)

BEFORE = {
    "app.couples": TableRows(count=1, digest="c0"),
    "app.pets": TableRows(count=2, digest="9e"),
    "auth.users": TableRows(count=2, digest="a5"),
}

CLEAN_DATA = """\
SET session_replication_role = replica;

COPY "app"."couples" ("id", "created_at") FROM stdin;
00000000-0000-4000-8000-0000000c0de1\t2026-11-22 10:00:00+00
\\.

COPY "auth"."users" ("id", "email") FROM stdin;
\\.

RESET ALL;
"""


def test_a_clean_dump_has_no_excluded_table() -> None:
    assert exclusion_problems(CLEAN_DATA) == []


def test_live_sessions_and_vector_buckets_in_the_dump_are_problems() -> None:
    data = CLEAN_DATA.replace(
        "RESET ALL;",
        'COPY "auth"."refresh_tokens" ("id", "token") FROM stdin;\n\\.\n\n'
        'COPY "storage"."buckets_vectors" ("id") FROM stdin;\n\\.\n\n'
        "RESET ALL;",
    )

    problems = exclusion_problems(data)

    assert len(problems) == 2
    assert any("auth.refresh_tokens" in problem for problem in problems)
    assert any("storage.buckets_vectors" in problem for problem in problems)


def test_the_same_rows_after_the_restore_are_no_difference() -> None:
    assert row_differences(BEFORE, dict(BEFORE)) == []


def test_a_table_that_lost_rows_is_a_difference() -> None:
    after = BEFORE | {"app.pets": TableRows(count=1, digest="7b")}

    assert row_differences(BEFORE, after) == [
        "app.pets had 2 rows before the dump and 1 after the restore."
    ]


def test_the_same_count_with_other_contents_is_a_difference() -> None:
    after = BEFORE | {"auth.users": TableRows(count=2, digest="ff")}

    assert row_differences(BEFORE, after) == [
        "auth.users has its 2 rows back, but not as they were dumped."
    ]


def test_a_table_missing_after_the_restore_is_a_difference() -> None:
    after = {name: rows for name, rows in BEFORE.items() if name != "app.couples"}

    assert row_differences(BEFORE, after) == [
        "app.couples had 1 rows before the dump and is gone after the restore."
    ]


def test_nothing_to_compare_proves_nothing() -> None:
    empty = {"app.couples": TableRows(count=0, digest="d4")}

    for before in ({}, empty):
        assert row_differences(before, before) == [
            "There were no rows to compare: the restore would pass on an empty "
            "database. Is the local seed loaded?"
        ]


def test_an_excluded_table_is_found_without_quotes_too() -> None:
    data = CLEAN_DATA.replace(
        "RESET ALL;", "COPY auth.sessions (id) FROM stdin;\n\\.\n\nRESET ALL;"
    )

    assert exclusion_problems(data) == [
        "data.sql copies auth.sessions, which the dump must leave out (ADR 0012)."
    ]


def test_a_dump_without_the_users_proves_nothing_about_exclusions() -> None:
    data = CLEAN_DATA.replace('COPY "auth"."users"', "-- no users")

    assert exclusion_problems(data) == [
        "data.sql has no COPY of auth.users, so its exclusions cannot be checked: "
        "did pg_dump's output change?"
    ]


MAIN_CONFIG = 'project_id = "twochi"\n\n[db]\nport = 55322\n'
SLOT_CONFIG = 'project_id = "twochi-s2"\n\n[db]\nport = 55522\n'


def checkout_at(folder: Path, config: str) -> Path:
    (folder / "supabase").mkdir(parents=True)
    (folder / "supabase" / "config.toml").write_text(config, encoding="utf-8")
    return folder


def test_a_slot_on_the_main_folders_config_is_not_its_own(tmp_path: Path) -> None:
    # The check would dump the main folder's database and then reset it.
    slot = tmp_path / ".claude" / "worktrees" / "slot-2"

    assert not has_own_config(checkout_at(slot, MAIN_CONFIG))


def test_a_slot_on_its_config_and_the_main_folder_have_their_own(
    tmp_path: Path,
) -> None:
    slot = tmp_path / "a" / ".claude" / "worktrees" / "slot-2"

    assert has_own_config(checkout_at(slot, SLOT_CONFIG))
    assert has_own_config(checkout_at(tmp_path / "b", MAIN_CONFIG))

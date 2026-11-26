"""Whether the local database is behind the repo's migrations, from names alone."""

from migration_drift import MigrationDrift, migration_drift

FIRST = "20261122000100_create_app_schema_and_api_role.sql"
SECOND = "20261122000200_create_couples_profiles_and_pets.sql"
AFFINITIES = "20261126000100_add_item_affinities.sql"


def test_a_database_with_every_migration_is_current() -> None:
    applied = [
        "20261122000100_create_app_schema_and_api_role",
        "20261122000200_create_couples_profiles_and_pets",
    ]

    assert migration_drift([FIRST, SECOND], applied) is None


def test_a_migration_the_database_has_not_applied_is_pending() -> None:
    applied = [
        "20261122000100_create_app_schema_and_api_role",
        "20261122000200_create_couples_profiles_and_pets",
    ]

    drift = migration_drift([FIRST, SECOND, AFFINITIES], applied)

    assert drift == MigrationDrift(pending=(AFFINITIES,), gone=())


def test_a_migration_renumbered_by_a_rebase_is_pending_and_its_old_one_gone() -> None:
    # The slot applied its branch's migration as 000100; main took that number first,
    # so the rebase moved the branch's one to 000200.
    applied = [
        "20261122000100_create_app_schema_and_api_role",
        "20261126000100_add_tastes_screen",
    ]
    renumbered = "20261126000200_add_tastes_screen.sql"

    drift = migration_drift([FIRST, AFFINITIES, renumbered], applied)

    assert drift == MigrationDrift(
        pending=(AFFINITIES, renumbered),
        gone=("20261126000100_add_tastes_screen",),
    )


def test_files_the_supabase_cli_would_not_apply_are_not_migrations() -> None:
    files = [FIRST, ".gitkeep", "README.md", "notes_20261130.sql"]

    assert (
        migration_drift(files, ["20261122000100_create_app_schema_and_api_role"])
        is None
    )


def test_the_message_names_what_differs_and_how_to_fix_it() -> None:
    drift = MigrationDrift(pending=(AFFINITIES,), gone=("20261126000900_add_bubbles",))

    message = drift.message()

    assert AFFINITIES in message
    assert "20261126000900_add_bubbles" in message
    assert "just reset" in message

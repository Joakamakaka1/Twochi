"""`just slot`: the config a slot gets, with no Docker and no git.

The shell around these functions (the worktree, `supabase start`) is run for real when a
slot is created.
"""

import tomllib

import pytest
from slot import slot_config

# The shape of supabase/config.toml: Twochi's ports are the 553xx ones; the others stay.
MAIN = """\
# A string used to distinguish different Supabase projects on the same host.
project_id = "twochi"

[api]
enabled = true
port = 55321
max_rows = 1000

[db]
port = 55322
shadow_port = 55320
major_version = 17

[db.pooler]
enabled = false
port = 55329

[studio]
port = 55323
api_url = "http://127.0.0.1"

[local_smtp]
port = 55324
# Uncomment to expose additional ports for testing user applications that send emails.
# smtp_port = 54325
# pop3_port = 54326

[auth]
site_url = "http://127.0.0.1:5173"

[auth.third_party.firebase]
enabled = false
# project_id = "my-firebase-project"

[edge_runtime]
inspector_port = 8083

[analytics]
port = 55327
"""


def changed_lines(before: str, after: str) -> dict[str, str]:
    lines = zip(before.splitlines(True), after.splitlines(True), strict=True)
    return {old.rstrip("\n"): new.rstrip("\n") for old, new in lines if old != new}


def test_a_slot_gets_its_own_project_and_ports_and_nothing_else_changes() -> None:
    assert changed_lines(MAIN, slot_config(MAIN, 1)) == {
        'project_id = "twochi"': 'project_id = "twochi-s1"',
        "port = 55321": "port = 55421",
        "port = 55322": "port = 55422",
        "shadow_port = 55320": "shadow_port = 55420",
        "port = 55329": "port = 55429",
        "port = 55323": "port = 55423",
        "port = 55324": "port = 55424",
        "port = 55327": "port = 55427",
    }


@pytest.mark.parametrize("slot", [2, 3, 9])
def test_each_slot_is_a_hundred_ports_further(slot: int) -> None:
    config = tomllib.loads(slot_config(MAIN, slot))

    assert config["project_id"] == f"twochi-s{slot}"
    assert config["db"]["port"] == 55322 + 100 * slot
    assert config["api"]["port"] == 55321 + 100 * slot


def test_a_twochi_port_inside_a_url_moves_too() -> None:
    # Left behind, the slot's Auth would send people to the main folder's instance.
    config = MAIN.replace('"http://127.0.0.1"', '"http://127.0.0.1:55321"')

    assert 'api_url = "http://127.0.0.1:55521"' in slot_config(config, 2)

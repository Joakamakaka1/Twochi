"""The environment for git commands that must act on the repository in their `cwd`.

Git exports GIT_DIR and its kin to a hook, as `git rev-parse --local-env-vars` lists
them. Inherited, they point every git command at the repository that runs the hook:
under the pre-push hook (TWO-26), a test's `git init` and `git config` for a throwaway
repository rewrote the real one's config.
"""

import os

LOCAL_GIT_VARIABLES = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_OBJECT_DIRECTORY",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_REPLACE_REF_BASE",
        "GIT_PREFIX",
        "GIT_SHALLOW_FILE",
        "GIT_COMMON_DIR",
    }
)


def git_environment() -> dict[str, str]:
    """This process's environment without the variables that tie git to a repository."""
    return {
        name: value
        for name, value in os.environ.items()
        if name not in LOCAL_GIT_VARIABLES
    }

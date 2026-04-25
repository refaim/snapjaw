"""Integration tests using real Git repositories.

These tests require network access and are skipped by default.
Run with: pytest -m integration

Test repositories (from TESTPLAN.md):
- https://github.com/refaim/MissingCrafts - vanilla addon
- https://github.com/refaim/MasterTradeSkills - vanilla addon
- https://github.com/fusionpit/QuestFrameFixer - has branch "1.12.1"
- https://github.com/refaim/LibCraftingProfessions-1.0 - NOT an addon (no .toc)
- https://gitlab.com/Artur91425/GrimoireKeeper - GitLab addon
"""

import os

import pytest

from gameversion import Expansion
from mygit import GitError, RemoteStateRequest, clone, fetch_states
from toc import find_addons

pytestmark = pytest.mark.integration


class TestCloneRealRepos:
    """Integration tests for cloning real repositories."""

    def test_clone_github_repo(self, tmp_path):
        """Clone a real GitHub repository."""
        repo = clone(
            "https://github.com/refaim/MissingCrafts.git",
            None,
            str(tmp_path / "repo"),
        )
        assert repo.workdir.endswith("/")
        assert os.path.isdir(repo.workdir)
        assert repo.head_commit_hex is not None

    def test_clone_with_branch(self, tmp_path):
        """Clone a specific branch from GitHub."""
        repo = clone(
            "https://github.com/fusionpit/QuestFrameFixer.git",
            "1.12.1",
            str(tmp_path / "repo"),
        )
        assert repo.branch == "1.12.1"

    def test_clone_nonexistent_repo_raises_error(self, tmp_path):
        """Cloning non-existent repo raises GitError."""
        with pytest.raises(GitError):
            clone(
                "https://github.com/this-user-does-not-exist-12345/no-such-repo.git",
                None,
                str(tmp_path / "repo"),
            )

    def test_clone_nonexistent_branch_raises_error(self, tmp_path):
        """Cloning non-existent branch raises GitError."""
        with pytest.raises(GitError):
            clone(
                "https://github.com/refaim/MissingCrafts.git",
                "this-branch-does-not-exist-12345",
                str(tmp_path / "repo"),
            )


class TestFetchStatesRealRepos:
    """Integration tests for fetching remote repository states."""

    def test_fetch_single_repo_state(self):
        """Fetch state of a real repository."""
        requests = [
            RemoteStateRequest("https://github.com/refaim/MissingCrafts.git", "master"),
        ]
        states = list(fetch_states(requests))
        assert len(states) == 1
        assert states[0].head_commit_hex is not None
        assert states[0].error is None

    def test_fetch_multiple_repos(self):
        """Fetch states of multiple repositories in parallel."""
        requests = [
            RemoteStateRequest("https://github.com/refaim/MissingCrafts.git", "master"),
            RemoteStateRequest("https://github.com/refaim/MasterTradeSkills.git", "master"),
        ]
        states = list(fetch_states(requests))
        assert len(states) == 2
        assert all(s.head_commit_hex is not None for s in states)

    def test_fetch_nonexistent_repo(self):
        """Fetching non-existent repo returns error state."""
        requests = [
            RemoteStateRequest(
                "https://github.com/this-user-does-not-exist-12345/no-such-repo.git",
                "master",
            ),
        ]
        states = list(fetch_states(requests))
        assert len(states) == 1
        assert states[0].error is not None


class TestFindAddonsRealRepos:
    """Integration tests for finding addons in cloned repositories."""

    def test_find_vanilla_addon(self, tmp_path):
        """Find addon in a vanilla WoW addon repository."""
        repo = clone(
            "https://github.com/refaim/MissingCrafts.git",
            None,
            str(tmp_path / "repo"),
        )
        addons = list(find_addons(repo.workdir, Expansion.Vanilla))
        assert len(addons) >= 1
        addon_names = {a.name for a in addons}
        assert "MissingCrafts" in addon_names

    def test_library_repo_no_addons(self, tmp_path):
        """Library repository (no .toc) returns no addons."""
        repo = clone(
            "https://github.com/refaim/LibCraftingProfessions-1.0.git",
            None,
            str(tmp_path / "repo"),
        )
        addons = list(find_addons(repo.workdir, Expansion.Vanilla))
        # Libraries typically don't have a .toc with proper Interface version
        # or their toc is for embedding, not standalone use
        assert len(addons) == 0

    def test_gitlab_repo(self, tmp_path):
        """Clone and find addon from GitLab."""
        repo = clone(
            "https://gitlab.com/Artur91425/GrimoireKeeper.git",
            None,
            str(tmp_path / "repo"),
        )
        addons = list(find_addons(repo.workdir, Expansion.Vanilla))
        assert len(addons) >= 1

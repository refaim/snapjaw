"""Tests for URL parsing logic in snapjaw cmd_install."""

from types import SimpleNamespace

import pytest

from snapjaw import CliError, Config, cmd_install


class TestUrlParsing:
    """Tests for repository URL parsing and normalization."""

    @pytest.fixture
    def run_install(self, monkeypatch, tmp_path):
        """Fixture to run cmd_install and capture the parsed URL/branch."""

        def _run(url, branch=None):
            calls = []

            def mock_install(config, repo_url, branch, addons_dir):
                calls.append((repo_url, branch))

            monkeypatch.setattr("snapjaw.install_addon", mock_install)

            args = SimpleNamespace(url=url, branch=branch, addons_dir=str(tmp_path))
            config = Config(addons_by_key={})
            cmd_install(config, args)
            return calls[0]

        return _run

    @pytest.mark.parametrize(
        "input_url,expected_url,expected_branch",
        [
            # GitHub URLs
            (
                "https://github.com/refaim/MissingCrafts",
                "https://github.com/refaim/MissingCrafts.git",
                None,
            ),
            (
                "https://github.com/refaim/MissingCrafts.git",
                "https://github.com/refaim/MissingCrafts.git",
                None,
            ),
            (
                "https://github.com/fusionpit/QuestFrameFixer/tree/1.12.1",
                "https://github.com/fusionpit/QuestFrameFixer.git",
                "1.12.1",
            ),
            # GitLab URLs
            (
                "https://gitlab.com/Artur91425/GrimoireKeeper",
                "https://gitlab.com/Artur91425/GrimoireKeeper.git",
                None,
            ),
            (
                "https://gitlab.com/Artur91425/GrimoireKeeper/-/tree/master",
                "https://gitlab.com/Artur91425/GrimoireKeeper.git",
                "master",
            ),
            # Non-GitHub/GitLab URL passed through
            (
                "https://custom.server/repo.git",
                "https://custom.server/repo.git",
                None,
            ),
        ],
        ids=[
            "github_simple",
            "github_with_git_suffix",
            "github_with_branch",
            "gitlab_simple",
            "gitlab_with_branch",
            "custom_url_passthrough",
        ],
    )
    def test_url_parsing(self, run_install, input_url, expected_url, expected_branch):
        """URL is correctly parsed and normalized."""
        repo_url, branch = run_install(input_url)
        assert repo_url == expected_url
        assert branch == expected_branch

    def test_explicit_branch_override(self, run_install):
        """Explicit --branch argument is used when URL has no branch."""
        repo_url, branch = run_install(
            "https://github.com/fusionpit/QuestFrameFixer",
            branch="1.12.1",
        )
        assert repo_url == "https://github.com/fusionpit/QuestFrameFixer.git"
        assert branch == "1.12.1"

    def test_branch_conflict_raises_error(self, run_install):
        """Conflicting branch in URL and --branch argument raises CliError."""
        with pytest.raises(CliError, match="requested branch"):
            run_install(
                "https://github.com/fusionpit/QuestFrameFixer/tree/1.12.1",
                branch="other-branch",
            )

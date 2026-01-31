"""Shared fixtures for snapjaw tests."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pygit2
import pytest

from snapjaw import Config, ConfigAddon, addon_key


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test (requires network)")
    config.addinivalue_line("markers", "slow: mark test as slow")


# Use a fixed naive datetime to match production code (datetime.now())
FIXED_NOW = datetime(2024, 6, 15, 12, 0, 0)


@pytest.fixture
def fixed_now():
    """Return a fixed datetime for testing."""
    return FIXED_NOW


@pytest.fixture
def make_addon(fixed_now):
    """Factory fixture for creating ConfigAddon instances."""

    def _make_addon(
        name="TestAddon",
        url="https://github.com/test/test.git",
        branch="master",
        commit="abc123",
        checksum=None,
        released_at=None,
        installed_at=None,
    ):
        return ConfigAddon(
            name=name,
            url=url,
            branch=branch,
            commit=commit,
            released_at=released_at or fixed_now,
            installed_at=installed_at or fixed_now,
            checksum=checksum,
        )

    return _make_addon


@pytest.fixture
def make_config(make_addon):
    """Factory fixture for creating Config instances."""

    def _make_config(*names):
        addons = {}
        for name in names:
            addons[addon_key(name)] = make_addon(name=name)
        return Config(addons_by_key=addons)

    return _make_config


@pytest.fixture
def make_toc_addon(tmp_path):
    """Factory fixture for creating addon directories with .toc files."""

    def _make_toc_addon(name, interface_version):
        addon_dir = tmp_path / name
        addon_dir.mkdir(parents=True, exist_ok=True)
        toc_content = f"## Interface: {interface_version}\n## Title: {name}\n"
        (addon_dir / f"{name}.toc").write_bytes(toc_content.encode("utf-8"))
        return addon_dir

    return _make_toc_addon


@pytest.fixture
def mock_tmpdir_context():
    """Context manager patch for mocking TemporaryDirectory."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value="/tmp/repo")
    mock.__exit__ = MagicMock(return_value=False)
    return patch("mygit.TemporaryDirectory", return_value=mock)


@pytest.fixture
def fetch_states_patches(mock_pygit2_repo, mock_tmpdir_context):
    """Combined patches for fetch_states tests.

    Returns a context manager with mocked pygit2 repo, GitError, sha1, and tmpdir.
    The sha1 mock is configured to return "abc123" as hexdigest.
    """
    from contextlib import ExitStack, contextmanager

    @contextmanager
    def _patches():
        with ExitStack() as stack:
            stack.enter_context(patch("mygit.pygit2.init_repository", return_value=mock_pygit2_repo))
            stack.enter_context(patch("mygit.pygit2.GitError", pygit2.GitError))
            mock_sha1 = stack.enter_context(patch("mygit.sha1"))
            mock_sha1.return_value.hexdigest.return_value = "abc123"
            stack.enter_context(mock_tmpdir_context)
            yield

    return _patches


@pytest.fixture
def mock_pygit2_repo():
    """Create a mocked pygit2.Repository."""
    repo = MagicMock()
    repo.remotes = MagicMock()
    repo.remotes.__iter__ = MagicMock(return_value=iter([]))
    repo.remotes.__getitem__ = MagicMock(side_effect=KeyError)
    return repo


@pytest.fixture
def mock_remote():
    """Factory fixture for creating mocked remotes."""

    def _mock_remote(name, url, refs=None, error=None):
        remote = MagicMock()
        remote.name = name
        remote.url = url
        if error:
            remote.ls_remotes.side_effect = pygit2.GitError(error)
        else:
            remote.ls_remotes.return_value = refs or []
        return remote

    return _mock_remote


@pytest.fixture
def mock_install_env(tmp_path, monkeypatch, fixed_now):
    """Setup mocked environment for install_addon tests.

    Returns a context manager that sets up repo_dir, mocks clone/TemporaryDirectory/signature,
    and provides addons_dir and config.
    """
    from contextlib import contextmanager

    from mygit import RepositoryInfo
    from snapjaw import Config

    @contextmanager
    def _setup(*, trailing_slash=True):
        addons_dir = tmp_path / "Addons"
        addons_dir.mkdir(exist_ok=True)

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir(exist_ok=True)

        workdir = str(repo_dir) + ("/" if trailing_slash else "")

        repo_info = RepositoryInfo(
            workdir=workdir,
            branch="master",
            head_commit_hex="abc123",
            head_commit_time=fixed_now,
        )
        monkeypatch.setattr("snapjaw.mygit.clone", lambda url, branch, path: repo_info)

        mock_tmpdir = MagicMock()
        mock_tmpdir.__enter__ = MagicMock(return_value=str(repo_dir))
        mock_tmpdir.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr("snapjaw.TemporaryDirectory", lambda: mock_tmpdir)
        monkeypatch.setattr("snapjaw.signature.calculate", lambda path: "sig|2")

        config = Config(addons_by_key={})
        config._loaded_from = str(tmp_path / "snapjaw.json")

        class Env:
            pass

        env = Env()
        env.addons_dir = addons_dir
        env.repo_dir = repo_dir
        env.config = config
        env.repo_info = repo_info

        yield env

    return _setup

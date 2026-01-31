"""Shared fixtures for snapjaw tests."""

from datetime import datetime
from unittest.mock import MagicMock

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

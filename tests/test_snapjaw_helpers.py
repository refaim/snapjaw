"""Tests for snapjaw helper functions and CLI argument parsing."""

import argparse
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from snapjaw import (
    CliError,
    addon_key,
    arg_type_dir,
    get_addon_from_config,
    main,
    parse_args,
    sort_addons_dict,
)


class TestAddonKey:
    """Tests for addon_key() - case-insensitive key generation."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("MyAddon", "myaddon"),
            ("myaddon", "myaddon"),
            ("Friend-O-Tron", "friend-o-tron"),
            ("UPPERCASE", "uppercase"),
        ],
    )
    def test_converts_to_lowercase(self, name, expected):
        """addon_key converts name to lowercase."""
        assert addon_key(name) == expected


class TestSortAddonsDict:
    """Tests for sort_addons_dict() - dictionary sorting."""

    def test_sorts_by_key(self):
        """Dictionary is sorted by keys."""
        d = {"b": 2, "a": 1, "c": 3}
        result = sort_addons_dict(d)
        assert list(result.keys()) == ["a", "b", "c"]

    def test_empty_dict(self):
        """Empty dictionary returns empty dictionary."""
        assert sort_addons_dict({}) == {}


class TestGetAddonFromConfig:
    """Tests for get_addon_from_config() - addon lookup by name."""

    def test_found(self, make_config):
        """Existing addon is returned."""
        config = make_config("MyAddon")
        addon = get_addon_from_config(config, "MyAddon")
        assert addon.name == "MyAddon"

    def test_case_insensitive(self, make_config):
        """Lookup is case-insensitive."""
        config = make_config("MyAddon")
        addon = get_addon_from_config(config, "myaddon")
        assert addon.name == "MyAddon"

    def test_not_found_raises_error(self, make_config):
        """Non-existent addon raises ArgumentTypeError."""
        config = make_config("MyAddon")
        with pytest.raises(argparse.ArgumentTypeError):
            get_addon_from_config(config, "NonExistent")


class TestArgTypeDir:
    """Tests for arg_type_dir() - directory path validation."""

    def test_valid_dir_returns_path(self, tmp_path):
        """Valid directory path is returned unchanged."""
        assert arg_type_dir(str(tmp_path)) == str(tmp_path)

    def test_invalid_dir_raises_error(self):
        """Non-existent directory raises ArgumentTypeError."""
        with pytest.raises(argparse.ArgumentTypeError, match="invalid directory path"):
            arg_type_dir("/nonexistent/dir")


class TestParseArgs:
    """Tests for parse_args() - CLI argument parsing."""

    def test_install_command(self, monkeypatch, tmp_path):
        """Install command parses URL argument."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "install", "https://example.com/repo.git"],
        )
        args = parse_args()
        assert args.url == "https://example.com/repo.git"

    def test_remove_command(self, monkeypatch, tmp_path):
        """Remove command parses addon names."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "remove", "MyAddon"],
        )
        args = parse_args()
        assert args.names == ["MyAddon"]

    def test_update_all(self, monkeypatch, tmp_path):
        """Update without names has empty names list."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "update"],
        )
        args = parse_args()
        assert args.names == []

    def test_update_specific(self, monkeypatch, tmp_path):
        """Update with names parses addon names."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "update", "MyAddon"],
        )
        args = parse_args()
        assert args.names == ["MyAddon"]

    def test_status_default_not_verbose(self, monkeypatch, tmp_path):
        """Status command defaults to non-verbose."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "status"],
        )
        args = parse_args()
        assert args.verbose is False

    def test_status_verbose_flag(self, monkeypatch, tmp_path):
        """Status -v flag sets verbose=True."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "status", "-v"],
        )
        args = parse_args()
        assert args.verbose is True

    def test_wow_dir_auto_detection(self, tmp_path, monkeypatch):
        """WoW directory is auto-detected from current working directory."""
        (tmp_path / "WoW.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])
        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)


class TestMain:
    """Tests for main() - application entry point."""

    def test_success_returns_zero(self, monkeypatch):
        """Successful execution returns 0."""
        mock_args = SimpleNamespace(callback=MagicMock())
        monkeypatch.setattr("snapjaw.parse_args", lambda: mock_args)
        assert main() == 0
        mock_args.callback.assert_called_once_with(mock_args)

    def test_cli_error_returns_one(self, monkeypatch):
        """CliError returns 1."""
        mock_args = SimpleNamespace(callback=MagicMock(side_effect=CliError("test error")))
        monkeypatch.setattr("snapjaw.parse_args", lambda: mock_args)
        assert main() == 1

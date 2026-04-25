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
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "install", "https://example.com/repo.git"],
        )
        args = parse_args()
        assert args.url == "https://example.com/repo.git"

    def test_remove_command(self, monkeypatch, tmp_path):
        """Remove command parses addon names."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "remove", "MyAddon"],
        )
        args = parse_args()
        assert args.names == ["MyAddon"]

    def test_update_all(self, monkeypatch, tmp_path):
        """Update without names has empty names list."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "update"],
        )
        args = parse_args()
        assert args.names == []

    def test_update_specific(self, monkeypatch, tmp_path):
        """Update with names parses addon names."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "update", "MyAddon"],
        )
        args = parse_args()
        assert args.names == ["MyAddon"]

    def test_status_default_not_verbose(self, monkeypatch, tmp_path):
        """Status command defaults to non-verbose."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "status"],
        )
        args = parse_args()
        assert args.verbose is False

    def test_status_verbose_flag(self, monkeypatch, tmp_path):
        """Status -v flag sets verbose=True."""
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(tmp_path), "--game-version", "vanilla", "status", "-v"],
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

        # Mock pefile.PE to report vanilla 1.12.x.
        fixed = MagicMock(FileVersionMS=(1 << 16) | 12, FileVersionLS=0)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "vanilla"

    def test_ascension_dir_auto_detection(self, tmp_path, monkeypatch):
        """Ascension.exe in game dir is detected and yields wotlk expansion."""
        (tmp_path / "Ascension.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        fixed = MagicMock(FileVersionMS=(3 << 16) | 3, FileVersionLS=(5 << 16) | 12340)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "wotlk"

    def test_game_version_override_flag(self, tmp_path, monkeypatch):
        """--game-version=wotlk overrides exe detection (no exe required)."""
        # Note: --addons-dir is provided so no walk-up is attempted.
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(addons_dir), "--game-version", "wotlk", "status"],
        )

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "wotlk"

    def test_game_version_override_no_exe_required(self, tmp_path, monkeypatch):
        """--game-version overrides also work when no exe exists anywhere."""
        # Empty tmp_path: no game dir, no exes.
        addons_dir = tmp_path / "Addons"
        addons_dir.mkdir()
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(addons_dir), "--game-version", "vanilla", "status"],
        )

        args = parse_args()
        assert args.expansion.value == "vanilla"

    def test_no_exe_no_override_raises_cli_error(self, tmp_path, monkeypatch):
        """No game dir + no override → CliError with actionable message."""
        # Empty tmp_path, no --addons-dir, no --game-version.
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        with pytest.raises(CliError, match=r"could not find game directory"):
            parse_args()

    def test_unsupported_major_raises_cli_error(self, tmp_path, monkeypatch):
        """Exe with unsupported major version (e.g. TBC 2.x) → CliError."""
        (tmp_path / "WoW.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        # 2.4.3 = TBC = unsupported.
        fixed = MagicMock(FileVersionMS=(2 << 16) | 4, FileVersionLS=(3 << 16) | 0)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        with pytest.raises(CliError, match=r"unsupported game version 2\."):
            parse_args()


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

"""Tests for gameversion.py — game directory and expansion detection."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gameversion import (
    Expansion,
    GameVersionError,
    Resolved,
    _find_game_dir,
    _read_expansion_from_exe,
    resolve,
)


class TestExpansion:
    def test_values(self):
        assert Expansion.Vanilla.value == "vanilla"
        assert Expansion.Wotlk.value == "wotlk"

    def test_construct_from_string(self):
        assert Expansion("vanilla") is Expansion.Vanilla
        assert Expansion("wotlk") is Expansion.Wotlk


class TestFindGameDir:
    def test_returns_dir_with_wow_exe(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        assert _find_game_dir(tmp_path) == tmp_path

    def test_returns_dir_with_ascension_exe(self, tmp_path):
        (tmp_path / "Ascension.exe").touch()
        assert _find_game_dir(tmp_path) == tmp_path

    def test_returns_dir_with_both_exes(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        (tmp_path / "Ascension.exe").touch()
        # Either exe is enough to identify the dir; result is the dir itself.
        assert _find_game_dir(tmp_path) == tmp_path

    def test_walks_up_from_nested_dir(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        nested = tmp_path / "Interface" / "Addons"
        nested.mkdir(parents=True)
        assert _find_game_dir(nested) == tmp_path

    def test_returns_none_when_no_exe_found(self, tmp_path):
        assert _find_game_dir(tmp_path) is None

    def test_walks_up_from_ascension_layout(self, tmp_path):
        # Mimics ...Ascension/Launcher/resources/epoch-live/Ascension.exe
        game_dir = tmp_path / "Launcher" / "resources" / "epoch-live"
        game_dir.mkdir(parents=True)
        (game_dir / "Ascension.exe").touch()
        nested = game_dir / "Interface" / "Addons"
        nested.mkdir(parents=True)
        assert _find_game_dir(nested) == game_dir


def _make_pe_mock(file_version_ms: int):
    """Build a MagicMock that quacks like a parsed pefile.PE with VS_FIXEDFILEINFO."""
    fixed = MagicMock()
    fixed.FileVersionMS = file_version_ms
    fixed.FileVersionLS = 0
    pe = MagicMock()
    pe.VS_FIXEDFILEINFO = [fixed]
    pe.parse_data_directories = MagicMock()
    return pe


def _ms(major: int, minor: int) -> int:
    return (major << 16) | minor


class TestReadExpansionFromExe:
    def test_wow_exe_vanilla(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(1, 12)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Vanilla

    def test_wow_exe_wotlk(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk

    def test_ascension_exe_wotlk(self, tmp_path, monkeypatch):
        (tmp_path / "Ascension.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk

    def test_ascension_priority_over_wow(self, tmp_path, monkeypatch):
        # Both files exist on disk. The MOCK is parameterised by which path
        # it gets; we verify _read_expansion_from_exe opens Ascension.exe first.
        (tmp_path / "WoW.exe").touch()
        (tmp_path / "Ascension.exe").touch()
        opened: list[str] = []

        def fake_pe(path, *a, **kw):
            opened.append(str(path))
            return _make_pe_mock(_ms(3, 3))

        monkeypatch.setattr("gameversion.pefile.PE", fake_pe)
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk
        assert opened == [str(tmp_path / "Ascension.exe")]

    def test_unsupported_major_tbc_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(2, 4)),
        )
        with pytest.raises(GameVersionError, match=r"unsupported game version 2\."):
            _read_expansion_from_exe(tmp_path)

    def test_no_exe_in_dir_raises(self, tmp_path):
        with pytest.raises(GameVersionError, match=r"no WoW\.exe or Ascension\.exe"):
            _read_expansion_from_exe(tmp_path)

    def test_pefile_failure_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()

        def boom(*a, **kw):
            raise Exception("malformed PE")

        monkeypatch.setattr("gameversion.pefile.PE", boom)
        with pytest.raises(GameVersionError, match=r"could not read version info"):
            _read_expansion_from_exe(tmp_path)

    def test_missing_vs_fixedfileinfo_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        pe = MagicMock()
        pe.parse_data_directories = MagicMock()
        # Simulate "no version resource": attribute not present.
        del pe.VS_FIXEDFILEINFO
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)
        with pytest.raises(GameVersionError, match=r"could not read version info"):
            _read_expansion_from_exe(tmp_path)


class TestResolve:
    # ---- happy paths ----

    def test_walk_up_from_addons_dir(self, tmp_path, monkeypatch):
        # game_dir/WoW.exe exists, cwd is game_dir/Interface/Addons,
        # neither --addons-dir nor --game-version provided.
        game_dir = tmp_path
        (game_dir / "WoW.exe").touch()
        addons_dir = game_dir / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(1, 12)),
        )

        result = resolve(addons_dir_arg=None, game_version_arg=None, cwd=addons_dir)

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Vanilla)

    def test_explicit_addons_dir_derives_game_dir(self, tmp_path, monkeypatch):
        game_dir = tmp_path
        (game_dir / "Ascension.exe").touch()
        addons_dir = game_dir / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )

        result = resolve(
            addons_dir_arg=str(addons_dir),
            game_version_arg=None,
            cwd=Path("/unrelated"),
        )

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Wotlk)

    def test_game_version_override_skips_exe_read(self, tmp_path, monkeypatch):
        # No exe anywhere on disk, but explicit override is given.
        addons_dir = tmp_path / "Addons"
        addons_dir.mkdir()
        # If we were to try opening any PE, this would blow up:
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: pytest.fail("pefile.PE must not be called when --game-version overrides"),
        )

        result = resolve(
            addons_dir_arg=str(addons_dir),
            game_version_arg="wotlk",
            cwd=Path("/unrelated"),
        )

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Wotlk)

    # ---- error paths ----

    def test_no_addons_dir_no_walk_up_match_raises(self, tmp_path):
        # cwd has no exe in any parent; no --addons-dir given.
        with pytest.raises(GameVersionError, match=r"could not find game directory"):
            resolve(addons_dir_arg=None, game_version_arg=None, cwd=tmp_path)

    def test_explicit_addons_dir_no_exe_no_override_raises(self, tmp_path):
        # game_dir would be tmp_path/.. — but there's no exe there either.
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        with pytest.raises(GameVersionError, match=r"could not detect game version"):
            resolve(
                addons_dir_arg=str(addons_dir),
                game_version_arg=None,
                cwd=Path("/unrelated"),
            )

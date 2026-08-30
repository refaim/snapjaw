"""Tests for the application version and CLI version flag."""

import re

import pytest

import version
from snapjaw import parse_args


class TestVersion:
    """Tests for the single source of truth version constant."""

    def test_has_three_numeric_components(self):
        """VERSION uses semantic versioning's three-component numeric form."""
        assert re.fullmatch(r"\d+\.\d+\.\d+", version.VERSION)


class TestVersionFlag:
    """Tests for the top-level --version flag."""

    @staticmethod
    def assert_version_output(monkeypatch, capsys, argv):
        monkeypatch.setattr("sys.argv", argv)

        with pytest.raises(SystemExit) as error:
            parse_args()

        assert error.value.code == 0
        captured = capsys.readouterr()
        assert captured.out == f"snapjaw {version.VERSION}\n"
        assert captured.err == ""

    def test_prints_exact_version(self, monkeypatch, capsys, tmp_path):
        """--version prints the application name and VERSION exactly."""
        self.assert_version_output(
            monkeypatch,
            capsys,
            [
                "snapjaw",
                "--addons-dir",
                str(tmp_path),
                "--game-version",
                "vanilla",
                "--version",
                "status",
            ],
        )

    def test_works_without_subcommand(self, monkeypatch, capsys):
        """--version exits before required subcommand validation."""
        self.assert_version_output(monkeypatch, capsys, ["snapjaw", "--version"])

    def test_works_outside_game_directory(self, monkeypatch, capsys, tmp_path):
        """--version exits before attempting to resolve an addons directory."""
        isolated_directory = tmp_path / "isolated"
        isolated_directory.mkdir()
        monkeypatch.chdir(isolated_directory)

        self.assert_version_output(monkeypatch, capsys, ["snapjaw", "--version"])

"""Tests for snapjaw CLI commands (install, remove, update, status)."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import gameversion
from mygit import GitError
from snapjaw import (
    AddonState,
    AddonStatus,
    CliError,
    Config,
    cmd_remove,
    cmd_status,
    cmd_update,
    install_addon,
    remove_addon_dir,
    run_command,
)
from toc import Addon


class TestRunCommand:
    """Tests for run_command() - command execution wrapper."""

    def test_missing_addons_dir_raises_error(self):
        """Missing addons_dir raises CliError."""
        args = SimpleNamespace(addons_dir=None)
        with pytest.raises(CliError, match="addons directory not found"):
            run_command(MagicMock(), False, args)

    def test_read_only_does_not_create_backup(self, tmp_path):
        """Read-only command doesn't create backup even if config exists."""
        config_path = tmp_path / "snapjaw.json"
        config_path.write_text('{"addons_by_key": {}}')
        callback = MagicMock()
        args = SimpleNamespace(addons_dir=str(tmp_path))
        run_command(callback, True, args)
        callback.assert_called_once()
        assert not (tmp_path / "snapjaw.backup.json").exists()

    def test_write_saves_config(self, tmp_path):
        """Write command saves config after execution."""
        callback = MagicMock()
        args = SimpleNamespace(addons_dir=str(tmp_path))
        run_command(callback, False, args)
        assert (tmp_path / "snapjaw.json").exists()

    def test_write_creates_backup(self, tmp_path):
        """Write command creates backup of existing config."""
        config_path = tmp_path / "snapjaw.json"
        config_path.write_text('{"addons_by_key": {}}')
        callback = MagicMock()
        args = SimpleNamespace(addons_dir=str(tmp_path))
        run_command(callback, False, args)
        assert (tmp_path / "snapjaw.backup.json").exists()

    def test_error_restores_backup(self, tmp_path, make_addon):
        """On error, backup is restored."""
        config_path = tmp_path / "snapjaw.json"
        config_path.write_text('{"addons_by_key": {}}')

        def bad_callback(config, args):
            config.addons_by_key["test"] = make_addon()
            config.save()
            raise RuntimeError("boom")

        args = SimpleNamespace(addons_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="boom"):
            run_command(bad_callback, False, args)

        with open(config_path) as f:
            restored = json.load(f)
        assert restored["addons_by_key"] == {}

    def test_read_only_error_does_not_restore_backup(self, tmp_path):
        """On error in read-only mode, no backup restoration is attempted."""
        config_path = tmp_path / "snapjaw.json"
        config_path.write_text('{"addons_by_key": {}}')

        def bad_callback(config, args):
            raise RuntimeError("boom")

        args = SimpleNamespace(addons_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="boom"):
            run_command(bad_callback, True, args)

        # Config unchanged, no backup was created or restored
        assert not (tmp_path / "snapjaw.backup.json").exists()


class TestInstallAddon:
    """Tests for install_addon() function."""

    def test_success(self, mock_install_env):
        """Successful install copies addon and updates config."""
        with mock_install_env() as env:
            addon_dir = env.repo_dir / "MyAddon"
            addon_dir.mkdir()
            (addon_dir / "MyAddon.toc").write_text("## Interface: 11200\n")
            (addon_dir / "init.lua").write_text("-- addon code")

            install_addon(
                env.config,
                "https://github.com/test/repo.git",
                "master",
                str(env.addons_dir),
                gameversion.Expansion.Vanilla,
            )

            assert "myaddon" in env.config.addons_by_key
            assert (env.addons_dir / "MyAddon" / "init.lua").exists()

    def test_git_error_raises_cli_error(self, tmp_path, monkeypatch):
        """Git clone failure raises CliError."""
        monkeypatch.setattr("snapjaw.mygit.clone", MagicMock(side_effect=GitError("auth failed")))

        config = Config(addons_by_key={})
        with pytest.raises(CliError, match="auth failed"):
            install_addon(
                config,
                "https://github.com/test/repo.git",
                None,
                str(tmp_path),
                gameversion.Expansion.Vanilla,
            )

    def test_no_addons_found_raises_error(self, mock_install_env, monkeypatch):
        """No matching addons in repo raises CliError naming the active expansion."""
        with mock_install_env() as env:
            monkeypatch.setattr("snapjaw.toc.find_addons", lambda workdir, expansion: iter([]))

            with pytest.raises(CliError, match="no vanilla addons found in repository"):
                install_addon(
                    env.config,
                    "https://github.com/test/repo.git",
                    None,
                    str(env.addons_dir),
                    gameversion.Expansion.Vanilla,
                )

    def test_no_addons_found_message_names_wotlk(self, mock_install_env, monkeypatch):
        """WotLK install with no compatible addons names wotlk in the error."""
        with mock_install_env() as env:
            monkeypatch.setattr("snapjaw.toc.find_addons", lambda workdir, expansion: iter([]))

            with pytest.raises(CliError, match="no wotlk addons found in repository"):
                install_addon(
                    env.config,
                    "https://github.com/test/repo.git",
                    None,
                    str(env.addons_dir),
                    gameversion.Expansion.Wotlk,
                )

    def test_copies_readme_from_root(self, mock_install_env):
        """Readme from repo root is copied to addon directory."""
        with mock_install_env() as env:
            addon_dir = env.repo_dir / "MyAddon"
            addon_dir.mkdir()
            (addon_dir / "MyAddon.toc").write_text("## Interface: 11200\n")
            (env.repo_dir / "README.txt").write_text("read me")

            install_addon(
                env.config,
                "https://github.com/test/repo.git",
                "master",
                str(env.addons_dir),
                gameversion.Expansion.Vanilla,
            )

            assert (env.addons_dir / "MyAddon" / "README.txt").read_text() == "read me"

    def test_addon_in_repo_root_skips_readme_copy(self, mock_install_env, monkeypatch):
        """When addon is in repo root (workdir == addon.path), readme copy is skipped."""
        with mock_install_env(trailing_slash=False) as env:
            (env.repo_dir / "MyAddon.toc").write_text("## Interface: 11200\n")
            (env.repo_dir / "README.txt").write_text("root readme")
            # Mock find_addons to return addon with path equal to workdir
            monkeypatch.setattr(
                "snapjaw.toc.find_addons", lambda workdir, expansion: iter([Addon("MyAddon", str(env.repo_dir))])
            )

            install_addon(
                env.config,
                "https://github.com/test/repo.git",
                "master",
                str(env.addons_dir),
                gameversion.Expansion.Vanilla,
            )

            # README exists because it was copied with the addon (copytree), not from root copy logic
            assert (env.addons_dir / "MyAddon" / "README.txt").read_text() == "root readme"

    def test_existing_readme_not_overwritten(self, mock_install_env):
        """Readme already in addon directory is not overwritten by root copy."""
        with mock_install_env() as env:
            addon_dir = env.repo_dir / "MyAddon"
            addon_dir.mkdir()
            (addon_dir / "MyAddon.toc").write_text("## Interface: 11200\n")
            (addon_dir / "README.txt").write_text("addon readme")
            (env.repo_dir / "README.txt").write_text("root readme")

            install_addon(
                env.config,
                "https://github.com/test/repo.git",
                "master",
                str(env.addons_dir),
                gameversion.Expansion.Vanilla,
            )

            # Addon's own readme is preserved, not overwritten by root readme
            assert (env.addons_dir / "MyAddon" / "README.txt").read_text() == "addon readme"


class TestCmdRemove:
    """Tests for cmd_remove() command."""

    def test_remove_existing_addon(self, tmp_path, make_config):
        """Existing addon is removed from config and disk."""
        addon_dir = tmp_path / "MyAddon"
        addon_dir.mkdir()
        (addon_dir / "file.lua").write_text("code")

        config = make_config("MyAddon")
        args = SimpleNamespace(names=["MyAddon"], addons_dir=str(tmp_path))
        cmd_remove(config, args)

        assert "myaddon" not in config.addons_by_key
        assert not addon_dir.exists()

    def test_remove_not_found_prints_message(self, tmp_path, make_config, capsys):
        """Removing non-existent addon prints message."""
        config = make_config()
        args = SimpleNamespace(names=["Missing"], addons_dir=str(tmp_path))
        cmd_remove(config, args)
        assert 'Addon not found: "Missing"' in capsys.readouterr().out


class TestRemoveAddonDir:
    """Tests for remove_addon_dir() function."""

    def test_removes_regular_dir(self, tmp_path):
        """Regular directory is removed with contents."""
        d = tmp_path / "addon"
        d.mkdir()
        (d / "file.txt").write_text("x")
        remove_addon_dir(str(d))
        assert not d.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_removes_symlink_not_target(self, tmp_path):
        """Symlink is removed but target directory remains."""
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target)
        remove_addon_dir(str(link))
        assert not link.exists()
        assert target.exists()

    def test_removes_symlink_via_islink(self, tmp_path, monkeypatch):
        """Symlink path detected via islink is removed with os.remove."""
        path = str(tmp_path / "fake_link")
        removed = []
        monkeypatch.setattr("snapjaw.os.path.islink", lambda p: True)
        monkeypatch.setattr("snapjaw.os.remove", lambda p: removed.append(p))
        remove_addon_dir(path)
        assert removed == [path]

    def test_nonexistent_path_is_noop(self, tmp_path):
        """Non-existent path does not raise error."""
        remove_addon_dir(str(tmp_path / "noexist"))

    def test_rmtree_symlink_error_falls_back_to_remove(self, tmp_path, monkeypatch):
        """When rmtree fails with symlink error, falls back to os.remove."""
        d = tmp_path / "addon"
        d.mkdir()

        remove_called = []

        def fake_rmtree(path):
            raise OSError("Cannot call rmtree on a symbolic link")

        def fake_remove(path):
            remove_called.append(path)

        monkeypatch.setattr("snapjaw.shutil.rmtree", fake_rmtree)
        monkeypatch.setattr("snapjaw.os.remove", fake_remove)
        remove_addon_dir(str(d))

        assert len(remove_called) == 1
        assert remove_called[0] == str(d)

    def test_rmtree_other_error_propagates(self, tmp_path, monkeypatch):
        """Non-symlink rmtree errors are re-raised."""
        d = tmp_path / "addon"
        d.mkdir()

        def fake_rmtree(path):
            raise OSError("permission denied")

        monkeypatch.setattr("snapjaw.shutil.rmtree", fake_rmtree)
        with pytest.raises(OSError, match="permission denied"):
            remove_addon_dir(str(d))


class TestCmdUpdate:
    """Tests for cmd_update() command."""

    def test_update_by_name(self, tmp_path, monkeypatch, make_config):
        """Update specific addon by name calls install_addon."""
        calls = []
        monkeypatch.setattr("snapjaw.install_addon", lambda config, url, branch, d, expansion: calls.append(url))

        config = make_config("MyAddon")
        args = SimpleNamespace(
            names=["MyAddon"],
            addons_dir=str(tmp_path),
            expansion=gameversion.Expansion.Vanilla,
        )
        cmd_update(config, args)
        assert len(calls) == 1

    def test_update_all_outdated(self, tmp_path, monkeypatch, make_config, fixed_now):
        """Update without names updates all outdated addons."""
        calls = []
        monkeypatch.setattr("snapjaw.install_addon", lambda config, url, branch, d, expansion: calls.append(url))
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [AddonState("MyAddon", AddonStatus.Outdated, None, fixed_now, fixed_now)],
        )

        config = make_config("MyAddon")
        args = SimpleNamespace(names=[], addons_dir=str(tmp_path), expansion=gameversion.Expansion.Vanilla)
        cmd_update(config, args)
        assert len(calls) == 1

    def test_update_no_outdated_prints_message(self, tmp_path, monkeypatch, make_config, fixed_now, capsys):
        """No outdated addons prints informational message."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [AddonState("MyAddon", AddonStatus.UpToDate, None, fixed_now, fixed_now)],
        )

        config = make_config("MyAddon")
        args = SimpleNamespace(names=[], addons_dir=str(tmp_path))
        cmd_update(config, args)
        assert "No addons to update found" in capsys.readouterr().out

    def test_update_with_error_prints_error(self, tmp_path, monkeypatch, make_config, fixed_now, capsys):
        """Addons with fetch errors print error message."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [AddonState("MyAddon", AddonStatus.Error, "timeout", fixed_now, fixed_now)],
        )

        config = make_config("MyAddon")
        args = SimpleNamespace(names=[], addons_dir=str(tmp_path))
        cmd_update(config, args)
        out = capsys.readouterr().out
        assert "Error: MyAddon: timeout" in out
        assert "No addons to update found" in out


class TestCmdStatus:
    """Tests for cmd_status() command."""

    def test_no_addons_prints_message(self, tmp_path, monkeypatch, capsys):
        """Empty addon list prints informational message."""
        monkeypatch.setattr("snapjaw.get_addon_states", lambda config, d: [])
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=False)
        cmd_status(config, args)
        assert "No addons found" in capsys.readouterr().out

    def test_with_addons_shows_table(self, tmp_path, monkeypatch, fixed_now, capsys):
        """Addons are displayed in table format."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [
                AddonState("MyAddon", AddonStatus.Outdated, None, fixed_now, fixed_now),
                AddonState("Other", AddonStatus.UpToDate, None, fixed_now, fixed_now),
            ],
        )
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=False)
        cmd_status(config, args)
        out = capsys.readouterr().out
        assert "MyAddon" in out
        assert "1 other addon is up to date" in out

    def test_verbose_shows_all_addons(self, tmp_path, monkeypatch, fixed_now, capsys):
        """Verbose mode shows up-to-date addons in table."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [
                AddonState("MyAddon", AddonStatus.UpToDate, None, fixed_now, fixed_now),
            ],
        )
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=True)
        cmd_status(config, args)
        out = capsys.readouterr().out
        assert "MyAddon" in out

    def test_with_errors_shows_error_column(self, tmp_path, monkeypatch, fixed_now, capsys):
        """Addons with errors show error message."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [
                AddonState("Bad", AddonStatus.Error, "connection refused", fixed_now, fixed_now),
            ],
        )
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=False)
        cmd_status(config, args)
        out = capsys.readouterr().out
        assert "connection refused" in out

    def test_all_up_to_date_shows_summary(self, tmp_path, monkeypatch, fixed_now, capsys):
        """All up-to-date shows count summary without table rows."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [
                AddonState("Addon1", AddonStatus.UpToDate, None, fixed_now, fixed_now),
                AddonState("Addon2", AddonStatus.UpToDate, None, fixed_now, fixed_now),
            ],
        )
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=False)
        cmd_status(config, args)
        out = capsys.readouterr().out
        assert "2 addons are up to date" in out

    def test_none_dates_handled(self, tmp_path, monkeypatch, capsys):
        """Addons with None dates (untracked) don't crash."""
        monkeypatch.setattr(
            "snapjaw.get_addon_states",
            lambda config, d: [
                AddonState("Untracked", AddonStatus.Untracked, None, None, None),
            ],
        )
        config = Config(addons_by_key={})
        args = SimpleNamespace(addons_dir=str(tmp_path), verbose=False)
        cmd_status(config, args)
        out = capsys.readouterr().out
        assert "Untracked" in out

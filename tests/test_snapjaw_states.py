"""Tests for snapjaw addon state detection (get_addon_states)."""

from mygit import RemoteState
from snapjaw import AddonStatus, Config, get_addon_states


class TestGetAddonStates:
    """Tests for get_addon_states() - detecting addon status.

    Note: get_addon_states() prints progress to stdout (e.g., "1/2").
    Tests use capsys to capture and verify this output.
    """

    def test_up_to_date(self, tmp_path, monkeypatch, make_addon, capsys):
        """Addon with matching commit and valid checksum is up-to-date."""
        addon_dir = tmp_path / "TestAddon"
        addon_dir.mkdir()
        (addon_dir / "init.lua").write_text("-- addon code")

        addon = make_addon(checksum="sig|2")
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", "abc123", None)]),
        )
        monkeypatch.setattr("snapjaw.signature.validate", lambda path, sig: True)

        states = get_addon_states(config, str(tmp_path))
        assert len(states) == 1
        assert states[0].status == AddonStatus.UpToDate

        # Verify progress was printed
        captured = capsys.readouterr()
        assert "1/1" in captured.out

    def test_outdated(self, tmp_path, monkeypatch, make_addon, capsys):
        """Addon with different remote commit is outdated."""
        addon_dir = tmp_path / "TestAddon"
        addon_dir.mkdir()
        (addon_dir / "init.lua").write_text("-- addon code")

        addon = make_addon(checksum="sig|2")
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", "newcommit", None)]),
        )
        monkeypatch.setattr("snapjaw.signature.validate", lambda path, sig: True)

        states = get_addon_states(config, str(tmp_path))
        assert states[0].status == AddonStatus.Outdated
        capsys.readouterr()  # Consume output

    def test_modified_invalid_checksum(self, tmp_path, monkeypatch, make_addon, capsys):
        """Addon with invalid checksum is marked as modified."""
        addon_dir = tmp_path / "TestAddon"
        addon_dir.mkdir()
        (addon_dir / "init.lua").write_text("-- modified code")

        addon = make_addon(checksum="sig|2")
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", "abc123", None)]),
        )
        monkeypatch.setattr("snapjaw.signature.validate", lambda path, sig: False)

        states = get_addon_states(config, str(tmp_path))
        assert states[0].status == AddonStatus.Modified
        capsys.readouterr()

    def test_modified_no_checksum(self, tmp_path, monkeypatch, make_addon, capsys):
        """Addon without checksum is marked as modified."""
        addon_dir = tmp_path / "TestAddon"
        addon_dir.mkdir()
        (addon_dir / "init.lua").write_text("-- addon code")

        addon = make_addon()  # checksum=None
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", "abc123", None)]),
        )

        states = get_addon_states(config, str(tmp_path))
        assert states[0].status == AddonStatus.Modified
        capsys.readouterr()

    def test_error(self, tmp_path, monkeypatch, make_addon, capsys):
        """Fetch error sets Error status with message."""
        addon = make_addon()
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", None, "timeout")]),
        )

        states = get_addon_states(config, str(tmp_path))
        assert states[0].status == AddonStatus.Error
        assert states[0].error == "timeout"
        capsys.readouterr()

    def test_unknown(self, tmp_path, monkeypatch, make_addon, capsys):
        """No commit and no error sets Unknown status."""
        addon = make_addon()
        config = Config(addons_by_key={"testaddon": addon})

        monkeypatch.setattr(
            "snapjaw.mygit.fetch_states",
            lambda reqs: iter([RemoteState("https://github.com/test/test.git", "master", None, None)]),
        )

        states = get_addon_states(config, str(tmp_path))
        assert states[0].status == AddonStatus.Unknown
        capsys.readouterr()

    def test_untracked(self, tmp_path, monkeypatch, capsys):
        """Directory not in config is Untracked."""
        (tmp_path / "SomeAddon").mkdir()
        config = Config(addons_by_key={})
        monkeypatch.setattr("snapjaw.mygit.fetch_states", lambda reqs: iter([]))

        states = get_addon_states(config, str(tmp_path))
        assert len(states) == 1
        assert states[0].status == AddonStatus.Untracked
        capsys.readouterr()

    def test_blizzard_addons_ignored(self, tmp_path, monkeypatch, capsys):
        """Blizzard_ prefixed directories are ignored."""
        (tmp_path / "Blizzard_UI").mkdir()
        config = Config(addons_by_key={})
        monkeypatch.setattr("snapjaw.mygit.fetch_states", lambda reqs: iter([]))

        states = get_addon_states(config, str(tmp_path))
        assert len(states) == 0
        capsys.readouterr()

    def test_missing(self, tmp_path, monkeypatch, make_addon, capsys):
        """Addon in config but not on disk is Missing."""
        addon = make_addon(name="MyMissingAddon")
        config = Config(addons_by_key={"mymissingaddon": addon})

        monkeypatch.setattr("snapjaw.mygit.fetch_states", lambda reqs: iter([]))

        states = get_addon_states(config, str(tmp_path))
        assert len(states) == 1
        assert states[0].status == AddonStatus.Missing
        # Verify original addon name is used, not lowercase key
        assert states[0].addon == "MyMissingAddon"
        capsys.readouterr()

    def test_multiple_addons_different_statuses(self, tmp_path, monkeypatch, make_addon, capsys):
        """Multiple addons with different statuses are correctly detected."""
        # Create addon directories with content
        (tmp_path / "UpToDateAddon").mkdir()
        (tmp_path / "UpToDateAddon" / "init.lua").write_text("-- code")
        (tmp_path / "OutdatedAddon").mkdir()
        (tmp_path / "OutdatedAddon" / "init.lua").write_text("-- code")
        (tmp_path / "UntrackedAddon").mkdir()

        addon1 = make_addon(
            name="UpToDateAddon", url="https://github.com/test/uptodate.git", commit="abc123", checksum="sig|2"
        )
        addon2 = make_addon(
            name="OutdatedAddon", url="https://github.com/test/outdated.git", commit="old123", checksum="sig|2"
        )
        config = Config(
            addons_by_key={
                "uptodateaddon": addon1,
                "outdatedaddon": addon2,
            }
        )

        def mock_fetch_states(reqs):
            for req in reqs:
                if "uptodate" in req.url:
                    yield RemoteState(req.url, "master", "abc123", None)
                elif "outdated" in req.url:
                    yield RemoteState(req.url, "master", "new456", None)

        monkeypatch.setattr("snapjaw.mygit.fetch_states", mock_fetch_states)
        monkeypatch.setattr("snapjaw.signature.validate", lambda path, sig: True)

        states = get_addon_states(config, str(tmp_path))
        status_by_name = {s.addon: s.status for s in states}

        assert status_by_name["UpToDateAddon"] == AddonStatus.UpToDate
        assert status_by_name["OutdatedAddon"] == AddonStatus.Outdated
        assert status_by_name["UntrackedAddon"] == AddonStatus.Untracked
        capsys.readouterr()

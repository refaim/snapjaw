"""Tests for toc.py - .toc file parsing and addon discovery."""

import pytest

from gameversion import Expansion
from toc import find_addons


class TestFindAddons:
    """Tests for finding WoW addons by parsing .toc files."""

    def test_simple_addon(self, make_toc_addon, tmp_path):
        """Single addon with valid Interface version is found."""
        make_toc_addon("MyAddon", 11200)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "MyAddon"

    @pytest.mark.parametrize(
        "version,expansion,expected_count",
        [
            (11200, Expansion.Vanilla, 1),  # vanilla addon found
            (20000, Expansion.Vanilla, 0),  # TBC addon filtered out
            (11201, Expansion.Vanilla, 0),  # version just above max
            (30000, Expansion.Wotlk, 1),  # wotlk lower bound
            (30300, Expansion.Wotlk, 1),  # wotlk upper bound
            (30301, Expansion.Wotlk, 0),  # just above wotlk upper
            (29999, Expansion.Wotlk, 0),  # just below wotlk lower
            (11200, Expansion.Wotlk, 0),  # vanilla TOC under wotlk client
            (30200, Expansion.Vanilla, 0),  # wotlk TOC under vanilla client
        ],
    )
    def test_version_filtering(self, make_toc_addon, tmp_path, version, expansion, expected_count):
        """Addons are filtered based on Interface version + expansion."""
        make_toc_addon("TestAddon", version)
        addons = list(find_addons(str(tmp_path), expansion))
        assert len(addons) == expected_count

    def test_multiple_addons_different_versions(self, make_toc_addon, tmp_path):
        """Only addons within version range are returned."""
        make_toc_addon("VanillaAddon", 11200)
        make_toc_addon("TBCAddon", 20000)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "VanillaAddon"

    def test_no_interface_header(self, tmp_path):
        """Addon without Interface header is skipped."""
        addon_dir = tmp_path / "NoHeader"
        addon_dir.mkdir()
        (addon_dir / "NoHeader.toc").write_text("## Title: NoHeader\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_multiple_addons(self, make_toc_addon, tmp_path):
        """Multiple valid addons are all found."""
        make_toc_addon("AddonA", 11200)
        make_toc_addon("AddonB", 11200)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 2
        names = {a.name for a in addons}
        assert names == {"AddonA", "AddonB"}

    def test_nested_addon_takes_outer(self, make_toc_addon, tmp_path):
        """When addon is nested inside another, only outer addon is returned."""
        outer = make_toc_addon("OuterAddon", 11200)
        inner_dir = outer / "InnerAddon"
        inner_dir.mkdir()
        (inner_dir / "InnerAddon.toc").write_text("## Interface: 11200\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "OuterAddon"

    def test_empty_dir(self, tmp_path):
        """Empty directory returns no addons."""
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_toc_case_insensitive(self, tmp_path):
        """Addon with .TOC extension (uppercase) is found."""
        addon_dir = tmp_path / "CaseAddon"
        addon_dir.mkdir()
        (addon_dir / "CaseAddon.TOC").write_text("## Interface: 11200\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1

    @pytest.mark.parametrize(
        "interface_line",
        [
            "## Interface: abc",
            "## Interface: ",
            "## Interface:",
            "##Interface: 11200",  # no space after ##
        ],
    )
    def test_invalid_interface_format_skipped(self, tmp_path, interface_line):
        """Invalid Interface format is skipped."""
        addon_dir = tmp_path / "BadAddon"
        addon_dir.mkdir()
        (addon_dir / "BadAddon.toc").write_text(f"{interface_line}\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_utf8_bom_encoding(self, tmp_path):
        """Addon with UTF-8 BOM encoding is found."""
        addon_dir = tmp_path / "BomAddon"
        addon_dir.mkdir()
        content = b"\xef\xbb\xbf## Interface: 11200\n## Title: BomAddon\n"
        (addon_dir / "BomAddon.toc").write_bytes(content)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1

    def test_windows_line_endings(self, tmp_path):
        """Addon with Windows line endings (CRLF) is found."""
        addon_dir = tmp_path / "WinAddon"
        addon_dir.mkdir()
        (addon_dir / "WinAddon.toc").write_bytes(b"## Interface: 11200\r\n## Title: WinAddon\r\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1

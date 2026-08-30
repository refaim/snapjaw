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

    @pytest.mark.parametrize(
        "folder,toc_versions,expansion,expected_name",
        [
            ("DBM-Core", [("DBM-Core", 30300), ("DBM-Core-WOTLKC", 30300)], Expansion.Wotlk, "DBM-Core"),
            ("DBM-Core", [("DBM-Core", 11200), ("DBM-Core-WOTLKC", 30300)], Expansion.Wotlk, "DBM-Core"),
            ("Foo", [("Foo", 11200), ("Foo_Wrath", 30300)], Expansion.Wotlk, "Foo"),
        ],
    )
    def test_addon_name_comes_from_folder(self, tmp_path, folder, toc_versions, expansion, expected_name):
        """Multi-TOC addons use their folder name, independent of the matching TOC stem."""
        addon_dir = tmp_path / folder
        addon_dir.mkdir()
        for toc_name, version in toc_versions:
            (addon_dir / f"{toc_name}.toc").write_text(f"## Interface: {version}\n")

        addons = list(find_addons(str(tmp_path), expansion))

        assert len(addons) == 1
        assert addons[0].name == expected_name

    def test_suffixed_only_toc_name_comes_from_stem(self, tmp_path):
        """A folder without its base TOC falls back to the compatible TOC stem."""
        addon_dir = tmp_path / "Foo"
        addon_dir.mkdir()
        (addon_dir / "Foo_Wrath.toc").write_text("## Interface: 30300\n")

        addons = list(find_addons(str(tmp_path), Expansion.Wotlk))

        assert len(addons) == 1
        assert addons[0].name == "Foo_Wrath"

    def test_folder_toc_name_match_is_case_insensitive(self, tmp_path):
        """A differently cased base TOC still preserves the folder name."""
        addon_dir = tmp_path / "Foo"
        addon_dir.mkdir()
        (addon_dir / "foo.toc").write_text("## Interface: 11200\n")

        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))

        assert len(addons) == 1
        assert addons[0].name == "Foo"

    def test_root_level_toc_name_comes_from_stem(self, tmp_path):
        """A repository-root addon keeps using the TOC stem instead of the clone directory name."""
        (tmp_path / "Root.toc").write_text("## Interface: 11200\n")

        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))

        assert len(addons) == 1
        assert addons[0].name == "Root"

    def test_unfiltered_scan_finds_every_interface_version_once_per_folder(self, tmp_path):
        """An unfiltered scan finds all valid Interface versions and deduplicates each folder."""
        mixed_dir = tmp_path / "Mixed"
        mixed_dir.mkdir()
        (mixed_dir / "Mixed.toc").write_text("## Interface: 11200\n")
        (mixed_dir / "Mixed_Wrath.toc").write_text("## Interface: 30300\n")

        vanilla_dir = tmp_path / "VanillaOnly"
        vanilla_dir.mkdir()
        (vanilla_dir / "VanillaOnly.toc").write_text("## Interface: 11200\n")

        wrath_dir = tmp_path / "WrathOnly"
        wrath_dir.mkdir()
        (wrath_dir / "WrathOnly.toc").write_text("## Interface: 30300\n")

        no_header_dir = tmp_path / "NoHeader"
        no_header_dir.mkdir()
        (no_header_dir / "NoHeader.toc").write_text("## Title: NoHeader\n")

        addons = list(find_addons(str(tmp_path), None))

        assert {addon.name for addon in addons} == {"Mixed", "VanillaOnly", "WrathOnly"}
        assert len(addons) == 3

    def test_unfiltered_scan_uses_suffixed_only_toc_stem(self, tmp_path):
        """An unfiltered scan also falls back when a folder has no base TOC."""
        addon_dir = tmp_path / "Foo"
        addon_dir.mkdir()
        (addon_dir / "Foo_Wrath.toc").write_text("## Interface: 30300\n")

        addons = list(find_addons(str(tmp_path), None))

        assert len(addons) == 1
        assert addons[0].name == "Foo_Wrath"

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

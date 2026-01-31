"""Tests for snapjaw Config and ConfigAddon classes."""

import json

import pytest

from snapjaw import Config, ConfigAddon


class TestConfigAddon:
    """Tests for ConfigAddon dataclass and serialization."""

    def test_serialize_deserialize_with_checksum(self, fixed_now):
        """ConfigAddon with checksum survives JSON round-trip."""
        addon = ConfigAddon(
            name="TestAddon",
            url="https://github.com/test/test.git",
            branch="master",
            commit="abc123",
            released_at=fixed_now,
            installed_at=fixed_now,
            checksum="hash|2",
        )
        json_str = addon.to_json()
        restored = ConfigAddon.from_json(json_str)
        assert restored.name == "TestAddon"
        assert restored.checksum == "hash|2"

    def test_serialize_deserialize_without_checksum(self, fixed_now):
        """ConfigAddon without checksum (None) survives JSON round-trip."""
        addon = ConfigAddon(
            name="TestAddon",
            url="https://github.com/test/test.git",
            branch="master",
            commit="abc123",
            released_at=fixed_now,
            installed_at=fixed_now,
        )
        json_str = addon.to_json()
        restored = ConfigAddon.from_json(json_str)
        assert restored.checksum is None


class TestConfig:
    """Tests for Config class - load/save operations."""

    def test_addon_name_to_key_lowercases(self):
        """addon_name_to_key converts to lowercase."""
        assert Config.addon_name_to_key("MyAddon") == "myaddon"
        assert Config.addon_name_to_key("UPPER") == "upper"
        assert Config.addon_name_to_key("already-lower") == "already-lower"

    def test_load_creates_new_if_not_exists(self, tmp_path):
        """load_or_setup creates empty config when file doesn't exist."""
        config_path = str(tmp_path / "snapjaw.json")
        config = Config.load_or_setup(config_path)
        assert config.addons_by_key == {}
        assert config._loaded_from == config_path

    def test_load_reads_existing_file(self, tmp_path):
        """load_or_setup reads existing config file."""
        config_path = str(tmp_path / "snapjaw.json")
        config = Config(addons_by_key={})
        config._loaded_from = config_path
        config.save()

        loaded = Config.load_or_setup(config_path)
        assert loaded.addons_by_key == {}
        assert loaded._loaded_from == config_path

    def test_load_with_addons(self, tmp_path, make_addon):
        """load_or_setup correctly deserializes addons."""
        config_path = str(tmp_path / "snapjaw.json")
        addon = make_addon()
        config = Config(addons_by_key={"testaddon": addon})
        config._loaded_from = config_path
        config.save()

        loaded = Config.load_or_setup(config_path)
        assert "testaddon" in loaded.addons_by_key
        assert loaded.addons_by_key["testaddon"].name == "TestAddon"

    def test_save_sorts_keys(self, tmp_path, make_addon):
        """save() writes addons sorted by key."""
        config_path = str(tmp_path / "snapjaw.json")
        config = Config(
            addons_by_key={
                "b": make_addon(name="B"),
                "a": make_addon(name="A"),
            }
        )
        config._loaded_from = config_path
        config.save()

        with open(config_path) as f:
            data = json.load(f)
        assert list(data["addons_by_key"].keys()) == ["a", "b"]

    def test_roundtrip_preserves_data(self, fixed_now):
        """Config survives JSON serialization round-trip."""
        addon = ConfigAddon(
            name="TestAddon",
            url="https://github.com/test/test.git",
            branch="master",
            commit="abc123",
            released_at=fixed_now,
            installed_at=fixed_now,
            checksum="hash|2",
        )
        config = Config(addons_by_key={"testaddon": addon})
        json_str = config.to_json()
        restored = Config.from_json(json_str)
        assert restored.addons_by_key["testaddon"].name == "TestAddon"
        assert restored.addons_by_key["testaddon"].checksum == "hash|2"

    def test_load_invalid_json_raises(self, tmp_path):
        """Corrupted JSON file raises JSONDecodeError."""
        config_path = tmp_path / "snapjaw.json"
        config_path.write_text("{invalid json")
        with pytest.raises(json.JSONDecodeError):
            Config.load_or_setup(str(config_path))

import hashlib

import pytest

from signature import _get_checksum, _hash, _pack, _unpack, calculate, validate


class TestPack:
    def test_format(self):
        assert _pack("abc123", 2) == "abc123|2"

    def test_round_trip(self):
        checksum = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        packed = _pack(checksum, 2)
        unpacked_checksum, unpacked_version = _unpack(packed)
        assert unpacked_checksum == checksum
        assert unpacked_version == 2


class TestUnpack:
    def test_with_version(self):
        checksum, version = _unpack("abc123|2")
        assert checksum == "abc123"
        assert version == 2

    def test_v1_no_separator(self):
        checksum, version = _unpack("abc123")
        assert checksum == "abc123"
        assert version == 1


class TestHash:
    def test_bytes(self):
        expected = hashlib.sha1(b"hello").hexdigest()
        assert _hash([b"hello"]) == expected

    def test_string(self):
        expected = hashlib.sha1(b"hello").hexdigest()
        assert _hash(["hello"]) == expected

    def test_multiple_chunks(self):
        expected = hashlib.sha1(b"helloworld").hexdigest()
        assert _hash([b"hello", b"world"]) == expected

    def test_mixed_types(self):
        expected = hashlib.sha1(b"helloworld").hexdigest()
        assert _hash([b"hello", "world"]) == expected

    def test_empty(self):
        expected = hashlib.sha1(b"").hexdigest()
        assert _hash([]) == expected


class TestCalculateValidate:
    def test_round_trip(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello world")
        sig = calculate(str(tmp_path))
        assert validate(str(tmp_path), sig)

    def test_modification_detected(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello world")
        sig = calculate(str(tmp_path))
        (tmp_path / "file.txt").write_text("changed")
        assert not validate(str(tmp_path), sig)

    def test_added_file_detected(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello")
        sig = calculate(str(tmp_path))
        (tmp_path / "new.txt").write_text("extra")
        assert not validate(str(tmp_path), sig)

    def test_empty_dir(self, tmp_path):
        sig = calculate(str(tmp_path))
        assert validate(str(tmp_path), sig)

    def test_nested_dirs(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "inner.txt").write_text("nested content")
        sig = calculate(str(tmp_path))
        assert validate(str(tmp_path), sig)

    def test_subdir_name_matters_v2(self, tmp_path):
        sub = tmp_path / "aaa"
        sub.mkdir()
        (sub / "file.txt").write_text("content")
        sig = calculate(str(tmp_path))

        # Recreate with different subdir name
        sub.rename(tmp_path / "bbb")
        assert not validate(str(tmp_path), sig)

    def test_missing_dir_raises(self):
        with pytest.raises(ValueError, match="not found"):
            calculate("/nonexistent/path")

    def test_invalid_version_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="Invalid hash version"):
            _get_checksum(str(tmp_path), version=99)

    def test_v1_backward_compat_single_file(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello")

        # A raw checksum without version separator is treated as v1
        v1_checksum = hashlib.sha1(hashlib.sha1(b"hello").hexdigest().encode("utf-8")).hexdigest()
        assert validate(str(tmp_path), v1_checksum)

    def test_v1_backward_compat_multiple_files(self, tmp_path):
        # V1 sorts file hashes, so order of creation shouldn't matter
        (tmp_path / "b.txt").write_text("second")
        (tmp_path / "a.txt").write_text("first")

        hash_a = hashlib.sha1(b"first").hexdigest()
        hash_b = hashlib.sha1(b"second").hexdigest()
        v1_checksum = hashlib.sha1("".join(sorted([hash_a, hash_b])).encode("utf-8")).hexdigest()
        assert validate(str(tmp_path), v1_checksum)

    def test_deleted_file_detected(self, tmp_path):
        """Deleting a file invalidates checksum."""
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "delete.txt").write_text("delete me")
        sig = calculate(str(tmp_path))
        (tmp_path / "delete.txt").unlink()
        assert not validate(str(tmp_path), sig)

    def test_renamed_file_detected(self, tmp_path):
        """Renaming a file invalidates checksum (v2 includes file paths)."""
        (tmp_path / "original.txt").write_text("content")
        sig = calculate(str(tmp_path))
        (tmp_path / "original.txt").rename(tmp_path / "renamed.txt")
        assert not validate(str(tmp_path), sig)

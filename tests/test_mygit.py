"""Tests for mygit.py - Git operations wrapper.

Tests focus on public API (clone, fetch_states) through behavior verification.
Internal implementation details are not tested directly.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from mygit import (
    GitError,
    RemoteState,
    RemoteStateRequest,
    RepositoryInfo,
    clone,
    fetch_states,
)


class TestClone:
    """Tests for the clone() function - cloning git repositories."""

    def test_success_returns_repository_info(self):
        """Successful clone returns RepositoryInfo with correct data."""
        expected = RepositoryInfo(
            workdir="/tmp/repo/",
            branch="master",
            head_commit_hex="abc123",
            head_commit_time=datetime(2024, 1, 1),
        )

        mock_data_conn = MagicMock()
        mock_data_conn.recv.return_value = expected
        mock_error_conn = MagicMock()
        mock_error_conn.poll.return_value = False

        with (
            patch("mygit.Pipe", side_effect=[(mock_data_conn, MagicMock()), (mock_error_conn, MagicMock())]),
            patch("mygit.Process") as mock_process_cls,
        ):
            mock_process_cls.return_value = MagicMock()

            result = clone("https://github.com/test/repo.git", "master", "/tmp/repo")

        assert result == expected

    def test_error_raises_git_error(self):
        """Clone failure raises GitError with message."""
        error = GitError("authentication failed")

        mock_data_conn = MagicMock()
        mock_error_conn = MagicMock()
        mock_error_conn.poll.return_value = True
        mock_error_conn.recv.return_value = error

        with (
            patch("mygit.Pipe", side_effect=[(mock_data_conn, MagicMock()), (mock_error_conn, MagicMock())]),
            patch("mygit.Process"),
            pytest.raises(GitError, match="authentication failed"),
        ):
            clone("https://github.com/test/repo.git", None, "/tmp/repo")


class TestFetchStates:
    """Tests for fetch_states() - checking remote repository states."""

    @pytest.fixture
    def mock_tmpdir_context(self):
        """Context manager for mocking TemporaryDirectory."""
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value="/tmp/repo")
        mock.__exit__ = MagicMock(return_value=False)
        return patch("mygit.TemporaryDirectory", return_value=mock)

    def test_success_returns_commit_hash(self, mock_remote, mock_pygit2_repo, mock_tmpdir_context):
        """Successful fetch returns commit hash for branch."""
        remote = mock_remote(
            "abc123",
            "https://github.com/test/repo.git",
            refs=[{"name": "refs/heads/master", "symref_target": "", "oid": "deadbeef"}],
        )
        mock_pygit2_repo.remotes.__iter__ = MagicMock(return_value=iter([remote]))

        with (
            patch("mygit.pygit2.init_repository", return_value=mock_pygit2_repo),
            patch("mygit.pygit2.GitError", Exception),
            patch("mygit.sha1") as mock_sha1,
            mock_tmpdir_context,
        ):
            mock_sha1.return_value.hexdigest.return_value = "abc123"

            requests = [RemoteStateRequest("https://github.com/test/repo.git", "master")]
            states = list(fetch_states(requests))

        assert len(states) == 1
        assert states[0].head_commit_hex == "deadbeef"
        assert states[0].error is None

    def test_head_symref_resolves_branch(self, mock_remote, mock_pygit2_repo, mock_tmpdir_context):
        """HEAD symref pointing to branch returns correct commit."""
        remote = mock_remote(
            "abc123",
            "https://github.com/test/repo.git",
            refs=[{"name": "HEAD", "symref_target": "refs/heads/main", "oid": "cafebabe"}],
        )
        mock_pygit2_repo.remotes.__iter__ = MagicMock(return_value=iter([remote]))

        with (
            patch("mygit.pygit2.init_repository", return_value=mock_pygit2_repo),
            patch("mygit.pygit2.GitError", Exception),
            patch("mygit.sha1") as mock_sha1,
            mock_tmpdir_context,
        ):
            mock_sha1.return_value.hexdigest.return_value = "abc123"

            requests = [RemoteStateRequest("https://github.com/test/repo.git", "main")]
            states = list(fetch_states(requests))

        assert len(states) == 1
        assert states[0].head_commit_hex == "cafebabe"

    def test_git_error_returns_error_state(self, mock_remote, mock_pygit2_repo, mock_tmpdir_context):
        """Git error returns state with error message, no commit."""
        remote = mock_remote(
            "abc123",
            "https://github.com/test/repo.git",
            error="connection refused",
        )
        mock_pygit2_repo.remotes.__iter__ = MagicMock(return_value=iter([remote]))

        with (
            patch("mygit.pygit2.init_repository", return_value=mock_pygit2_repo),
            patch("mygit.pygit2.GitError", Exception),
            patch("mygit.sha1") as mock_sha1,
            mock_tmpdir_context,
        ):
            mock_sha1.return_value.hexdigest.return_value = "abc123"

            requests = [RemoteStateRequest("https://github.com/test/repo.git", "master")]
            states = list(fetch_states(requests))

        assert len(states) == 1
        assert states[0].error == "connection refused"
        assert states[0].head_commit_hex is None

    def test_existing_remote_reused(self, mock_remote, mock_pygit2_repo, mock_tmpdir_context):
        """Existing remote is reused, not recreated."""
        remote = mock_remote("abc123", "https://github.com/test/repo.git", refs=[])
        mock_pygit2_repo.remotes.__iter__ = MagicMock(return_value=iter([remote]))
        mock_pygit2_repo.remotes.__getitem__ = MagicMock(return_value=remote)

        with (
            patch("mygit.pygit2.init_repository", return_value=mock_pygit2_repo),
            patch("mygit.pygit2.GitError", Exception),
            patch("mygit.sha1") as mock_sha1,
            mock_tmpdir_context,
        ):
            mock_sha1.return_value.hexdigest.return_value = "abc123"

            requests = [RemoteStateRequest("https://github.com/test/repo.git", "master")]
            list(fetch_states(requests))

        mock_pygit2_repo.remotes.create.assert_not_called()


class TestCloneInternalProcess:
    """Tests for _clone() - the subprocess worker function.

    These test the actual clone logic that runs in a subprocess.
    We mock pygit2 to avoid real network calls.
    """

    def test_success_sends_repository_info(self):
        """Successful clone sends RepositoryInfo through data connection."""
        mock_commit = MagicMock()
        mock_commit.id = "abc123"
        mock_commit.commit_time = 1704067200  # 2024-01-01 00:00:00 UTC

        mock_head = MagicMock()
        mock_head.target = "ref"
        mock_head.shorthand = "master"

        mock_repo = MagicMock()
        mock_repo.workdir = "/tmp/repo/"
        mock_repo.head = mock_head
        mock_repo.__getitem__ = MagicMock(return_value=mock_commit)

        data_conn = MagicMock()
        error_conn = MagicMock()

        from mygit import _clone

        with patch("mygit.pygit2") as mock_pygit2:
            mock_pygit2.clone_repository.return_value = mock_repo
            mock_pygit2.Commit = type(mock_commit)
            _clone("https://github.com/test/repo.git", "master", "/tmp/repo", data_conn, error_conn)

        data_conn.send.assert_called_once()
        info = data_conn.send.call_args[0][0]
        assert info.workdir == "/tmp/repo/"
        assert info.branch == "master"
        error_conn.send.assert_not_called()

    def test_git_error_sends_error(self):
        """Git error sends GitError through error connection."""
        data_conn = MagicMock()
        error_conn = MagicMock()

        from mygit import _clone

        with patch("mygit.pygit2") as mock_pygit2:
            mock_pygit2.GitError = Exception
            mock_pygit2.clone_repository.side_effect = Exception("auth failed")
            _clone("https://github.com/test/repo.git", None, "/tmp/repo", data_conn, error_conn)

        error_conn.send.assert_called_once()
        sent_error = error_conn.send.call_args[0][0]
        assert isinstance(sent_error, GitError)
        data_conn.send.assert_not_called()

    def test_key_error_sends_error(self):
        """KeyError (bad branch) sends GitError through error connection."""
        data_conn = MagicMock()
        error_conn = MagicMock()

        from mygit import _clone

        with patch("mygit.pygit2") as mock_pygit2:
            mock_pygit2.GitError = Exception
            mock_pygit2.clone_repository.side_effect = KeyError("bad branch")
            _clone("https://github.com/test/repo.git", "nonexistent", "/tmp/repo", data_conn, error_conn)

        error_conn.send.assert_called_once()
        data_conn.send.assert_not_called()


class TestGitProgressCallbacks:
    """Tests for _GitProgressCallbacks - progress reporting during clone.

    Tests verify output format contains expected substrings, not exact text.
    """

    def test_sideband_progress_prints(self, capsys):
        """sideband_progress prints message."""
        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        cb.sideband_progress("remote: Counting objects")
        captured = capsys.readouterr()
        assert "remote: Counting objects" in captured.out

    def test_transfer_progress_receiving_objects(self, capsys):
        """Receiving objects shows percentage."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        progress = SimpleNamespace(
            received_objects=50,
            total_objects=100,
            received_bytes=1024,
            indexed_deltas=0,
            total_deltas=0,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert "50%" in captured.out

    def test_transfer_progress_objects_done(self, capsys):
        """Completed objects shows 'done'."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        progress = SimpleNamespace(
            received_objects=100,
            total_objects=100,
            received_bytes=2048,
            indexed_deltas=0,
            total_deltas=0,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_transfer_progress_indexing_deltas(self, capsys):
        """Indexing deltas shows percentage after objects done."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        cb._objects_done = True
        progress = SimpleNamespace(
            received_objects=100,
            total_objects=100,
            received_bytes=2048,
            indexed_deltas=5,
            total_deltas=10,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert "50%" in captured.out

    def test_transfer_progress_deltas_done(self, capsys):
        """Completed deltas shows 'done'."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        cb._objects_done = True
        progress = SimpleNamespace(
            received_objects=100,
            total_objects=100,
            received_bytes=2048,
            indexed_deltas=10,
            total_deltas=10,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_transfer_progress_zero_deltas_skipped(self, capsys):
        """Zero total deltas produces no output."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        cb._objects_done = True
        progress = SimpleNamespace(
            received_objects=100,
            total_objects=100,
            received_bytes=2048,
            indexed_deltas=0,
            total_deltas=0,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_transfer_progress_after_all_done_no_output(self, capsys):
        """After both objects and deltas done, no output."""
        from types import SimpleNamespace

        from mygit import _GitProgressCallbacks

        cb = _GitProgressCallbacks()
        cb._objects_done = True
        cb._deltas_done = True
        progress = SimpleNamespace(
            received_objects=100,
            total_objects=100,
            received_bytes=2048,
            indexed_deltas=10,
            total_deltas=10,
        )
        cb.transfer_progress(progress)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestHasRemote:
    """Tests for _has_remote() helper function."""

    def test_remote_exists(self):
        """Returns True when remote exists."""
        from mygit import _has_remote

        repo = MagicMock()
        repo.remotes.__getitem__ = MagicMock(return_value=MagicMock())
        assert _has_remote(repo, "origin") is True

    def test_remote_not_exists(self):
        """Returns False when remote doesn't exist."""
        from mygit import _has_remote

        repo = MagicMock()
        repo.remotes.__getitem__ = MagicMock(side_effect=KeyError)
        assert _has_remote(repo, "origin") is False


class TestDataClasses:
    """Tests for data classes - ensure they hold expected data."""

    def test_repository_info_fields(self):
        """RepositoryInfo stores all required fields."""
        info = RepositoryInfo(
            workdir="/tmp/repo/",
            branch="master",
            head_commit_hex="abc123",
            head_commit_time=datetime(2024, 1, 1),
        )
        assert info.workdir == "/tmp/repo/"
        assert info.branch == "master"
        assert info.head_commit_hex == "abc123"

    def test_remote_state_fields(self):
        """RemoteState stores URL, branch, commit, and error."""
        state = RemoteState(
            url="https://github.com/test/repo.git",
            branch="master",
            head_commit_hex="abc123",
            error=None,
        )
        assert state.url == "https://github.com/test/repo.git"
        assert state.error is None

    def test_remote_state_request_fields(self):
        """RemoteStateRequest stores URL and branch."""
        request = RemoteStateRequest(
            url="https://github.com/test/repo.git",
            branch="master",
        )
        assert request.url == "https://github.com/test/repo.git"
        assert request.branch == "master"

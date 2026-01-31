import math
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from tempfile import TemporaryDirectory

import humanize
import pygit2


class GitError(RuntimeError):
    pass


@dataclass
class RepositoryInfo:
    workdir: str
    branch: str
    head_commit_hex: str
    head_commit_time: datetime


# Workaround for https://github.com/libgit2/pygit2/issues/264
def clone(url: str, branch: str | None, path: str) -> RepositoryInfo:
    def make_pipe() -> tuple[Connection, Connection]:
        return Pipe()

    parent_data_conn, child_data_conn = make_pipe()
    parent_error_conn, child_error_conn = make_pipe()

    process = Process(target=_clone, args=(url, branch, path, child_data_conn, child_error_conn))
    process.start()
    process.join()

    if parent_error_conn.poll(0):
        raise parent_error_conn.recv()

    result: RepositoryInfo = parent_data_conn.recv()
    return result


def _clone(url: str, branch: str | None, path: str, data_conn: Connection, error_conn: Connection):
    try:
        repo: pygit2.Repository = pygit2.clone_repository(
            url, path, depth=1, checkout_branch=branch, callbacks=_GitProgressCallbacks()
        )
    except (pygit2.GitError, KeyError) as error:
        error_conn.send(GitError(str(error)))
        return
    head = repo[repo.head.target]
    assert isinstance(head, pygit2.Commit)
    info = RepositoryInfo(
        workdir=repo.workdir,
        branch=repo.head.shorthand,
        head_commit_hex=str(head.id),
        head_commit_time=datetime.fromtimestamp(head.commit_time),
    )
    data_conn.send(info)


class _GitProgressCallbacks(pygit2.RemoteCallbacks):
    def __init__(self):
        super().__init__()
        self._objects_done = False
        self._deltas_done = False
        self._max_progress_len = 0

    def sideband_progress(self, progress: str) -> None:
        print(progress, end="\r")

    def transfer_progress(self, progress: pygit2.remotes.TransferProgress) -> None:
        def print_progress(prefix: str, suffix: str, cur_count: int, max_count: int) -> None:
            eol = "\r"
            text = f"{prefix}: {math.ceil(cur_count / max_count * 100)}% ({cur_count}/{max_count}) {suffix}"
            if cur_count == max_count:
                eol = "\n"
                text = f"{text.strip()}, done."
            self._max_progress_len = max(self._max_progress_len, len(text))
            print(text.ljust(self._max_progress_len), end=eol)

        if not self._objects_done:
            a, b = progress.received_objects, progress.total_objects
            size = humanize.naturalsize(progress.received_bytes)
            print_progress("Receiving objects", f"[{size}]", a, b)
            self._objects_done = a >= b
        elif not self._deltas_done:
            a, b = progress.indexed_deltas, progress.total_deltas
            if b > 0:
                print_progress("Indexing deltas", "", a, b)
                self._deltas_done = a >= b


@dataclass
class RemoteStateRequest:
    url: str
    branch: str


@dataclass
class RemoteState:
    url: str
    branch: str
    head_commit_hex: str | None
    error: str | None


@dataclass
class _RemoteLsResult:
    remote: pygit2.Remote
    refs: list[dict]
    error: str | None


def fetch_states(requests: list[RemoteStateRequest]) -> Iterator[RemoteState]:
    with TemporaryDirectory() as repo_dir:
        repo = pygit2.init_repository(repo_dir)
        remote_name_to_branches: dict[str, list[str]] = {}
        for request in requests:
            name = sha1(request.url.encode("utf-8")).hexdigest()
            if not _has_remote(repo, name):
                repo.remotes.create(name, request.url)
            remote_name_to_branches.setdefault(name, []).append(request.branch)

        def ls(remote: pygit2.Remote) -> _RemoteLsResult:
            try:
                refs = remote.ls_remotes()
                error = None
            except pygit2.GitError as exception:
                refs = []
                error = str(exception)
            return _RemoteLsResult(remote, refs, error)

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(ls, remote) for remote in repo.remotes]
            for future in as_completed(futures):
                ls_result: _RemoteLsResult = future.result()

                remote_name = ls_result.remote.name
                assert remote_name is not None
                for branch in remote_name_to_branches[remote_name]:
                    url = ls_result.remote.url or ""
                    if ls_result.error is not None:
                        yield RemoteState(url, branch, None, ls_result.error)
                    else:
                        branch_ref = f"refs/heads/{branch}"
                        for ref in ls_result.refs:
                            is_head = ref["name"] == "HEAD" and ref["symref_target"] == branch_ref
                            if is_head or ref["name"] == branch_ref:
                                yield RemoteState(url, branch, str(ref["oid"]), None)
                                break


def _has_remote(repo: pygit2.Repository, name: str) -> bool:
    try:
        repo.remotes.__getitem__(name)
        return True
    except KeyError:
        return False

import hashlib
import os
from typing import Generator

_LATEST_VERSION = 2


def calculate(dirpath: str) -> str:
    return _pack(_get_checksum(dirpath, _LATEST_VERSION), _LATEST_VERSION)


def validate(dirpath: str, signature: str) -> bool:
    checksum, version = _unpack(signature)
    return checksum == _get_checksum(dirpath, version)


def _pack(checksum: str, version) -> str:
    return f'{checksum}|{version}'


def _unpack(signature: str) -> tuple[str, int]:
    if '|' not in signature:
        return signature, 1
    checksum, version = signature.split('|')
    return checksum, int(version)


def _get_checksum(dirpath: str, version: int) -> str:
    if not os.path.isdir(dirpath):
        raise ValueError(f'Directory "{dirpath}" not found')
    if version == 1:
        chunks = sorted(_get_dir_chunks_v1(dirpath))
    elif version == 2:
        chunks = _get_dir_chunks_v2(dirpath)
    else:
        raise RuntimeError('Invalid hash version')
    return _hash(chunks)


def _get_dir_chunks_v1(dirpath: str) -> Generator[str, None, None]:
    for current_root, _, filenames in os.walk(dirpath):
        for filename in sorted(filenames):
            yield _hash(_get_file_chunks(os.path.join(current_root, filename)))


def _get_dir_chunks_v2(dirpath: str) -> Generator[str, None, None]:
    for current_root, subdirs, files in os.walk(dirpath):
        yield from sorted(subdirs)
        for filename in sorted(files):
            filepath = os.path.join(current_root, filename)
            yield os.path.relpath(filepath, dirpath)
            yield _hash(_get_file_chunks(filepath))


def _get_file_chunks(filepath: str) -> Generator[bytes, None, None]:
    with open(filepath, 'rb') as filehandle:
        while True:
            data = filehandle.read(64 * 1024)
            if not data:
                break
            yield data


def _hash(chunks: Generator[bytes|str, None, None]) -> str:
    hasher = hashlib.sha1()
    for chunk in chunks:
        if isinstance(chunk, str):
            chunk = chunk.encode('utf-8')
        hasher.update(chunk)
    return hasher.hexdigest()

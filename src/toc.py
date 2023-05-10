import os
import re
from dataclasses import dataclass
from typing import Generator


@dataclass
class Addon:
    name: str
    path: str
    game_version: int


class ParseError(RuntimeError):
    pass


def find_addons(directory) -> Generator[Addon, None, None]:
    for toc_path in _find_toc_files(directory):
        match = re.search(r'## Interface:\s+(?P<v>\d+)', _read(toc_path))
        if not match:
            raise ParseError(f'Unable to detect addon interface version in toc file "{toc_path}"')
        yield Addon(
            name=os.path.splitext(os.path.basename(toc_path))[0],
            path=os.path.dirname(toc_path),
            game_version=int(match.groupdict()['v']))


def _find_toc_files(directory) -> Generator[str, None, None]:
    for directory, _, files in os.walk(directory):
        for filename in files:
            if os.path.splitext(filename.lower())[1] == '.toc':
                yield os.path.join(directory, filename)


def _read(path: str) -> str:
    for encoding in ['utf-8', None]:
        with open(path, encoding=encoding) as fp:
            try:
                return fp.read()
            except UnicodeDecodeError:
                pass
    raise ParseError(f'Unable to guess encoding of {path}')

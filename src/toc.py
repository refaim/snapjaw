import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


@dataclass
class Addon:
    name: str
    path: str


@dataclass
class _TocFile:
    path: Path
    game_version: int


class ParseError(RuntimeError):
    pass


def find_addons(dir_path: str, max_game_version: int) -> Generator[Addon, None, None]:
    def sort_key(toc: _TocFile) -> int:
        return len(toc.path.parents)

    addon_paths = []
    for toc_file in sorted(_find_toc_files(dir_path, max_game_version), key=sort_key):
        if all(parent not in addon_paths for parent in toc_file.path.parents):
            yield Addon(name=toc_file.path.stem, path=str(toc_file.path.parent))
            addon_paths.append(toc_file.path.parent)


def _find_toc_files(root_dir: str, max_game_version: int) -> Generator[_TocFile, None, None]:
    for path in Path(root_dir).rglob('*'):
        if path.is_file() and path.suffix.lower() == '.toc':
            match = re.search(r'## Interface:\s+(?P<v>\d+)', _read(path))
            if match:
                game_version = int(match.groupdict()['v'])
                if game_version <= max_game_version:
                    yield _TocFile(path, game_version)


def _read(path: Path) -> str:
    for encoding in ['utf-8', None]:
        with path.open(encoding=encoding) as fp:
            try:
                return fp.read()
            except UnicodeDecodeError:
                pass
    raise ParseError(f'Unable to guess encoding of {path}')

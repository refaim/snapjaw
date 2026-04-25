import re
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from gameversion import Expansion


@dataclass
class Addon:
    name: str
    path: str


@dataclass
class _TocFile:
    path: Path
    game_version: int


def find_addons(dir_path: str, expansion: Expansion) -> Generator[Addon, None, None]:
    def sort_key(toc: _TocFile) -> int:
        return len(toc.path.parents)

    addon_paths = []
    for toc_file in sorted(_find_toc_files(dir_path, expansion), key=sort_key):
        if all(parent not in addon_paths for parent in toc_file.path.parents):
            yield Addon(name=toc_file.path.stem, path=str(toc_file.path.parent))
            addon_paths.append(toc_file.path.parent)


def _find_toc_files(root_dir: str, expansion: Expansion) -> Generator[_TocFile, None, None]:
    for path in Path(root_dir).rglob("*"):
        if path.is_file() and path.suffix.lower() == ".toc":
            game_version = _get_game_version(path)
            if game_version is not None and _interface_matches(game_version, expansion):
                yield _TocFile(path, game_version)


def _interface_matches(version: int, expansion: Expansion) -> bool:
    if expansion is Expansion.Vanilla:
        return version <= 11200
    if expansion is Expansion.Wotlk:
        return 30000 <= version <= 30300
    raise AssertionError(f"unhandled expansion: {expansion}")  # pragma: no cover


def _get_game_version(toc_path: Path) -> int | None:
    regexp = re.compile(b"## Interface: *(?P<v>[0-9]+)")
    with toc_path.open(mode="rb") as fp:
        for line in fp:
            match = regexp.search(line)
            if match:
                return int(match.groupdict()["v"])
    return None

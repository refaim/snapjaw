"""Game version detection from WoW client executable.

Resolves the addons directory and which expansion the user is on by reading
the PE VS_FIXEDFILEINFO of WoW.exe / Ascension.exe.
"""

import enum
from dataclasses import dataclass
from pathlib import Path

import pefile  # type: ignore[import-untyped]

# Priority order: Ascension wins when both exes coexist (D2 in spec).
_EXE_NAMES: tuple[str, ...] = ("Ascension.exe", "WoW.exe")


class Expansion(enum.Enum):
    Vanilla = "vanilla"
    Wotlk = "wotlk"


_MAJOR_TO_EXPANSION: dict[int, Expansion] = {
    1: Expansion.Vanilla,
    3: Expansion.Wotlk,
}


class GameVersionError(RuntimeError):
    """Raised when the game directory or its executable cannot be resolved
    into a known expansion."""


@dataclass(frozen=True)
class Resolved:
    addons_dir: Path
    expansion: Expansion


def _find_game_dir(start: Path) -> Path | None:
    """Walk up from `start` (inclusive) toward the filesystem root.
    Return the first directory that contains any of `_EXE_NAMES`,
    or None if no such directory is found.

    Any match is sufficient to identify the directory; the priority
    order in `_EXE_NAMES` is enforced later by `_read_expansion_from_exe`.
    """
    current = start
    while True:
        if any((current / name).is_file() for name in _EXE_NAMES):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _read_expansion_from_exe(game_dir: Path) -> Expansion:
    """Open the first existing exe from `_EXE_NAMES` (Ascension > WoW),
    read VS_FIXEDFILEINFO via pefile, and map the major version to
    `Expansion`.

    Raises:
        GameVersionError: if no supported exe exists in `game_dir`,
            if pefile cannot read version info, or if the major
            version is not in `_MAJOR_TO_EXPANSION`.
    """
    exe_path: Path | None = None
    for name in _EXE_NAMES:
        candidate = game_dir / name
        if candidate.is_file():
            exe_path = candidate
            break
    if exe_path is None:
        raise GameVersionError(
            f"could not detect game version: no WoW.exe or Ascension.exe in {game_dir}; "
            f"specify --game-version"
        )

    try:
        pe = pefile.PE(str(exe_path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        fixed_info = pe.VS_FIXEDFILEINFO[0]
        file_version_ms = fixed_info.FileVersionMS
        file_version_ls = fixed_info.FileVersionLS
    # pefile surfaces a wide variety of exception types from its parser
    # (PEFormatError, AttributeError on missing VS_FIXEDFILEINFO, IndexError
    # on empty version-resource lists, etc.). Catch broadly and reframe.
    except Exception as error:
        raise GameVersionError(
            f"could not read version info from {exe_path}: {error}; specify --game-version"
        ) from error

    major = (file_version_ms >> 16) & 0xFFFF
    minor = file_version_ms & 0xFFFF
    patch = (file_version_ls >> 16) & 0xFFFF

    expansion = _MAJOR_TO_EXPANSION.get(major)
    if expansion is None:
        raise GameVersionError(
            f"unsupported game version {major}.{minor}.{patch} in {exe_path} "
            f"(supported: 1.x vanilla, 3.x wotlk); use --game-version to override"
        )
    return expansion


def resolve(
    addons_dir_arg: str | None,
    game_version_arg: str | None,
    cwd: Path,
) -> Resolved:
    """Resolve `(addons_dir, expansion)` from CLI arguments and CWD.

    Resolution order:
      1. game_dir = (addons_dir_arg/../..) if addons_dir_arg else _find_game_dir(cwd)
      2. addons_dir = addons_dir_arg or game_dir/Interface/Addons
      3. expansion = Expansion(game_version_arg) if provided,
                     else _read_expansion_from_exe(game_dir)

    Raises:
        GameVersionError: with an actionable message on any failure.
    """
    if addons_dir_arg is not None:
        addons_dir_path = Path(addons_dir_arg)
        game_dir = addons_dir_path.parent.parent
    else:
        found = _find_game_dir(cwd)
        if found is None:
            raise GameVersionError(
                "could not find game directory: no WoW.exe or Ascension.exe in current "
                "directory or any parent; specify --addons-dir and --game-version"
            )
        game_dir = found
        addons_dir_path = game_dir / "Interface" / "Addons"

    expansion = (
        Expansion(game_version_arg)
        if game_version_arg is not None
        else _read_expansion_from_exe(game_dir)
    )

    return Resolved(addons_dir=addons_dir_path, expansion=expansion)

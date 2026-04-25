# WotLK 3.3.5 support — design

## Goal

Extend snapjaw beyond vanilla so it also works for WotLK 3.3.5 clients
(both stock 3.3.5a Wow.exe and custom launchers like Project Ascension's
`Ascension.exe`). The tool determines which expansion the user is on by
reading the game executable, and filters TOC files accordingly.

## Decisions (locked during brainstorming)

1. **Detection mechanism:** read PE `VS_FIXEDFILEINFO` from the exe; map
   the major version (1 → vanilla, 3 → wotlk). No filename heuristics.
2. **Failure handling:** hard error with actionable message; user can
   bypass via `--game-version=vanilla|wotlk`.
3. **TOC filter rule:**
   - Vanilla: `Interface <= 11200` (current behaviour, unchanged).
   - Wotlk: `30000 <= Interface <= 30300`.
4. **CLI override:** `--game-version=vanilla|wotlk`. When set, autodetect
   is skipped entirely and the exe is not opened.
5. **`game_dir` resolution:**
   - If `--addons-dir` given → `game_dir = addons_dir/../..`.
   - Else walk up from CWD looking for `Ascension.exe` or `WoW.exe`.
6. **Both exes present in the same folder:** prefer `Ascension.exe` over
   `WoW.exe`.
7. **PE parsing library:** `pefile` (added with `uv add pefile`, no
   manual version pin).
8. **Architecture split:** new module `gameversion.py` owns exe-reading
   and game-dir resolution; the per-expansion TOC matching rule lives in
   `toc.py` next to existing TOC logic; `snapjaw.py` is the CLI glue.

## Architecture overview

```
parse_args() ──→ argparse: --addons-dir, --game-version
       │
       ▼
gameversion.resolve(addons_dir_arg, game_version_arg, cwd)
       │  → Resolved(addons_dir: Path, expansion: Expansion)
       ▼
run_command → cmd_install/update/remove/status
       │
       ▼
install_addon(..., expansion) → toc.find_addons(workdir, expansion)
       │
       ▼
toc._interface_matches(version, expansion) gates each .toc file
```

## Components

### `gameversion.py` (new)

```python
class Expansion(enum.Enum):
    Vanilla = "vanilla"
    Wotlk = "wotlk"

_MAJOR_TO_EXPANSION = {1: Expansion.Vanilla, 3: Expansion.Wotlk}
_EXE_NAMES = ("Ascension.exe", "WoW.exe")  # priority order (Ascension wins)

class GameVersionError(RuntimeError):
    """Raised when game directory or exe cannot be resolved."""

@dataclass(frozen=True)
class Resolved:
    addons_dir: Path
    expansion: Expansion

def resolve(addons_dir_arg: str | None,
            game_version_arg: str | None,
            cwd: Path) -> Resolved: ...

def _find_game_dir(start: Path) -> Path | None:
    """Walks up from `start` looking for a directory containing one of
    `_EXE_NAMES`. Returns first match or None."""

def _read_expansion_from_exe(game_dir: Path) -> Expansion:
    """Picks first existing exe in `_EXE_NAMES` order (Ascension > WoW),
    reads VS_FIXEDFILEINFO via pefile, maps major to Expansion.
    Raises GameVersionError on missing exe / missing resources / unsupported major."""
```

`resolve` algorithm (matches the data-flow section below):

1. **game_dir:** if `addons_dir_arg` is set →
   `Path(addons_dir_arg).parent.parent`; else `_find_game_dir(cwd)` (may
   be `None`).
2. **addons_dir:** if `addons_dir_arg` set → that path; else if game_dir
   resolved → `game_dir / "Interface" / "Addons"`; else
   `GameVersionError("could not find game directory: no WoW.exe or Ascension.exe in current directory or any parent; specify --addons-dir and --game-version")`.
3. **expansion:** if `game_version_arg` set →
   `Expansion(game_version_arg)` (override wins, exe untouched); else if
   game_dir resolved → `_read_expansion_from_exe(game_dir)`; else
   `GameVersionError("could not detect game version, specify --game-version")`.

### `toc.py` (modified)

```python
# Old:
# def find_addons(dir_path: str, max_game_version: int) -> Generator[Addon, None, None]
# New:
def find_addons(dir_path: str, expansion: Expansion) -> Generator[Addon, None, None]

def _interface_matches(version: int, expansion: Expansion) -> bool:
    match expansion:
        case Expansion.Vanilla:
            return version <= 11200
        case Expansion.Wotlk:
            return 30000 <= version <= 30300
```

The internal `_TocFile`, `_get_game_version`, and the
"shortest-path-wins" addon-deduplication logic stay as-is. Only the
filter predicate and the public signature change.

### `snapjaw.py` (modified)

- `parse_args()`:
  - Drop the inline walk-up block (current lines 82–91).
  - Add `--game-version` argument:
    `parser.add_argument("--game-version", choices=["vanilla", "wotlk"], default=None)`.
  - After `parser.parse_args()`, call
    `gameversion.resolve(args.addons_dir, args.game_version, Path.cwd())`
    and overwrite `args.addons_dir`, set `args.expansion = resolved.expansion`.
- `arg_type_dir` stays as the argparse-level "directory exists" check
  for explicit `--addons-dir`.
- `install_addon(...)` gains an `expansion: Expansion` parameter; the
  hard-coded `toc.find_addons(repo.workdir, 11200)` becomes
  `toc.find_addons(repo.workdir, expansion)`.
- `cmd_install` and `cmd_update` pass `args.expansion` to
  `install_addon`.
- `run_command` keeps its `addons_dir` existence check unchanged.
- `main()` catches `gameversion.GameVersionError` and re-raises as
  `CliError` (or wraps inline) so output goes through the existing
  `error: <message>` stderr path.

### `pyproject.toml`

`uv add pefile` (no manual pin — let uv resolve).

### `README.md`

- Features section: add "Detects game version automatically (vanilla
  1.12, WotLK 3.3.5); supports `WoW.exe` and `Ascension.exe`".
- Usage examples: mention the `--game-version` override flag with one
  example for the case "snapjaw is run outside the game directory".
- Drop wording that implies vanilla-only support where appropriate.

## Data flow

End-to-end on `snapjaw <cmd>`:

1. `argparse` produces `args.addons_dir` (str | None) and
   `args.game_version` (str | None).
2. `gameversion.resolve(...)` → `Resolved(addons_dir, expansion)`.
   - Resolves `game_dir` (from `--addons-dir/../..` or walk-up).
   - Resolves `addons_dir` (explicit, or `game_dir/Interface/Addons`).
   - Resolves `expansion` (override wins, otherwise reads exe).
3. `args.addons_dir` is overwritten with the resolved path; new
   `args.expansion` is set.
4. `run_command` proceeds as today (config load, command dispatch).
5. `install_addon(..., expansion)` calls
   `toc.find_addons(workdir, expansion)`.
6. `_find_toc_files` keeps only `.toc` files where `_interface_matches`
   returns true; `find_addons` deduplicates nested addons exactly as
   today.

`_read_expansion_from_exe(game_dir)` is invoked **only** when no
`--game-version` override was passed; with the override, the exe is
never opened.

## Error handling

All gameversion-level failures raise `gameversion.GameVersionError` and
surface to the user as `error: <message>` via the existing CLI plumbing.

| Situation | Message |
|---|---|
| No `--addons-dir`, walk-up failed, no `--game-version` | `could not find game directory: no WoW.exe or Ascension.exe in current directory or any parent; specify --addons-dir and --game-version` |
| `--addons-dir` does not exist | (existing `arg_type_dir` ArgumentTypeError stays unchanged) |
| `--addons-dir` set, no exe in `<addons_dir>/../..`, no `--game-version` | `could not detect game version: no WoW.exe or Ascension.exe in <game_dir>; specify --game-version` |
| Exe present but `pefile` fails / no `VS_FIXEDFILEINFO` | `could not read version info from <exe_path>: <reason>; specify --game-version` |
| Exe read OK, major is not 1 or 3 | `unsupported game version <major>.<minor>.<patch> in <exe_path> (supported: 1.x vanilla, 3.x wotlk); use --game-version to override` |
| Invalid `--game-version` value | argparse handles via `choices` |

Every detection-failure message ends with the same escape hatch:
`--game-version`. This is the user contract — automation by default,
explicit override always available.

No config-format migration is needed: `snapjaw.json` schema is
unchanged.

## Testing

### `tests/test_gameversion.py` (new)

Fixtures: a callable `make_fake_exe(name, file_version_tuple)` that
writes a small PE file to `tmp_path` with the requested
`VS_FIXEDFILEINFO`. Implementation approach: commit one minimal
template PE (~4 KB) under `tests/fixtures/template.exe`; the fixture
loads it with `pefile`, mutates the version, and writes the modified
file. Deterministic, no compile-time dependencies.

Cases:

- `_read_expansion_from_exe`:
  - `WoW.exe` with `(1, 12, 1, 5875)` → `Expansion.Vanilla`.
  - `Ascension.exe` with `(3, 3, 5, 12340)` → `Expansion.Wotlk`.
  - `WoW.exe` with `(2, 4, 3, ...)` → `GameVersionError`
    ("unsupported game version 2.x").
  - Exe with no resource section → `GameVersionError`
    ("could not read version info").
  - Both `Ascension.exe` (3.x) and `WoW.exe` (1.x) in same folder →
    returns `Wotlk` (Ascension priority).
- `_find_game_dir`:
  - Only `WoW.exe` in folder → returned.
  - Only `Ascension.exe` in folder → returned.
  - Both → returned (single dir; priority is for exe-reading, not
    dir-finding).
  - Neither → `None`.
  - CWD deeply nested under game dir → walks up and returns game dir.
- `resolve` happy-path:
  - `addons_dir_arg=None, cwd=<game_dir>/Interface/Addons` (vanilla
    fake exe present) → `Resolved(<game_dir>/Interface/Addons,
    Vanilla)`.
  - `addons_dir_arg=<absolute path>, game_version_arg=None` → derives
    game_dir from `../..`, reads exe.
  - `game_version_arg="wotlk"` and no exe anywhere → returns
    `Wotlk` without touching the filesystem for exes.
- `resolve` error-path: one test per row of the error-handling table.

### `tests/test_toc.py` (modified)

Replace `find_addons(str(tmp_path), 11200)` with
`find_addons(str(tmp_path), Expansion.Vanilla)` throughout. Add a
parametrized `test_wotlk_version_filtering` covering the rule
boundaries:

| `Interface` | `Expansion` | Found? |
|---|---|---|
| 11200 | Vanilla | ✓ |
| 11200 | Wotlk | ✗ |
| 29999 | Wotlk | ✗ |
| 30000 | Wotlk | ✓ |
| 30300 | Wotlk | ✓ |
| 30301 | Wotlk | ✗ |
| 30200 | Vanilla | ✗ |

### `tests/test_snapjaw_helpers.py`

- Existing walk-up-by-`WoW.exe` test (line ~145) stays.
- Add an analogous walk-up-by-`Ascension.exe` test.
- Add a test for `--game-version=wotlk` overriding autodetect (no exe
  on disk).

### `tests/test_integration.py` and `tests/test_snapjaw_commands.py`

Mechanical: replace integer game-version arguments with the new
`Expansion` enum value where they call `find_addons` directly. No
behavioural changes for vanilla-only tests.

### CI

Already runs on Linux and Windows. PE parsing via `pefile` is
cross-platform. No new CI configuration needed.

## Out of scope

- TBC, Cataclysm, MoP, or other expansions. Adding a new expansion
  later is a 4-line patch (`Expansion.Tbc = "tbc"` + entry in
  `_MAJOR_TO_EXPANSION` + a `case` in `_interface_matches` + argparse
  choice). Not needed now.
- Multi-TOC addons (`Foo.toc` + `Foo-Wrath.toc` in the same folder).
  Existing snapjaw already deduplicates by addon directory, picking the
  first matching `.toc` (filesystem-dependent). Behaviour is unchanged
  by this design and may be addressed separately if it shows up as a
  real problem on WotLK addons.
- `snapjaw.json` config schema changes or migrations.
- Changing the vanilla TOC filter rule to `1xxxx` for symmetry with the
  wotlk rule. Explicitly rejected — vanilla stays at `<= 11200`.

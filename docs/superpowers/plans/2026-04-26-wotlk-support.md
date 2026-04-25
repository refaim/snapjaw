# WotLK 3.3.5 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add WotLK 3.3.5 client support to snapjaw so it works with both vanilla `WoW.exe` (Turtle WoW etc.) and WotLK clients including Project Ascension's `Ascension.exe`, with game version determined automatically by reading the executable's PE `VS_FIXEDFILEINFO`.

**Architecture:** New `gameversion.py` module owns exe-reading and game-dir resolution; `toc.py` gains a per-expansion `Interface` filter rule (vanilla `<= 11200` unchanged, wotlk `30000–30300`); `snapjaw.py` becomes the CLI glue that calls `gameversion.resolve(...)` to obtain `(addons_dir, expansion)` and threads `expansion` through to `toc.find_addons`.

**Tech Stack:** Python 3.12, `pefile` (new), `pygit2`, `pytest`, `argparse`, `pathlib`. Build via `uv`. Linting via `ruff`, type-checking via `mypy`. CI runs on Linux + Windows.

**Reference spec:** `docs/superpowers/specs/2026-04-26-wotlk-support-design.md` (decisions and constraints).

**Plan execution rule (project-wide):** Tasks end with a verification step. **Do not run `git commit` automatically** — the user controls commit timing. Each task should leave the working tree in a state that is reviewable and committable, but the actual commit is initiated only on explicit user request.

---

## File Map

**Create:**
- `src/gameversion.py` — `Expansion` enum, `Resolved` dataclass, `GameVersionError`, `_find_game_dir`, `_read_expansion_from_exe`, `resolve`.
- `tests/test_gameversion.py` — unit tests for the above (mocks `pefile.PE`).

**Modify:**
- `src/toc.py` — change `find_addons` signature to take `Expansion`; add `_interface_matches`.
- `src/snapjaw.py` — replace inline walk-up with `gameversion.resolve(...)`; add `--game-version` CLI flag; thread `expansion` through `install_addon`.
- `tests/test_toc.py` — switch existing tests to `Expansion.Vanilla`; add wotlk boundary tests.
- `tests/test_snapjaw_helpers.py` — fix existing `test_wow_dir_auto_detection`; add Ascension walk-up test, override test, error-message tests.
- `tests/test_snapjaw_commands.py` — pass `Expansion.Vanilla` through `install_addon` calls and update `find_addons` mock signatures.
- `tests/test_integration.py` — switch `find_addons` calls to use `Expansion.Vanilla`.
- `pyproject.toml` — add `pefile` dependency (via `uv add pefile`).
- `README.md` — update Features section, mention supported clients (`WoW.exe`, `Ascension.exe`) and the `--game-version` override.

---

## Task 1: Add `pefile` dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add the dependency via `uv`**

Run:
```bash
uv add pefile
```

Expected: `uv` resolves a recent version of `pefile`, updates `pyproject.toml` (`dependencies` list grows by one line), and refreshes `uv.lock`.

- [ ] **Step 2: Verify `pefile` is importable**

Run:
```bash
uv run python -c "import pefile; print(pefile.__version__)"
```

Expected: a version string is printed (e.g. `2024.8.26` or newer); no `ImportError`.

- [ ] **Step 3: Run the existing test suite to confirm nothing broke**

Run:
```bash
uv run pytest -q
```

Expected: full pass — adding a dependency must not change behaviour.

- [ ] **Step 4: Verification gate**

Working tree changes are limited to `pyproject.toml` and `uv.lock`. No code change. Hand back to user for review/commit (do NOT commit automatically).

---

## Task 2: Create `gameversion.py` module skeleton

**Files:**
- Create: `src/gameversion.py`
- Create: `tests/test_gameversion.py`

- [ ] **Step 1: Write a failing test for the `Expansion` enum**

Create `tests/test_gameversion.py`:

```python
"""Tests for gameversion.py — game directory and expansion detection."""

from gameversion import Expansion


class TestExpansion:
    def test_values(self):
        assert Expansion.Vanilla.value == "vanilla"
        assert Expansion.Wotlk.value == "wotlk"

    def test_construct_from_string(self):
        assert Expansion("vanilla") is Expansion.Vanilla
        assert Expansion("wotlk") is Expansion.Wotlk
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_gameversion.py -v
```

Expected: collection error / `ModuleNotFoundError: No module named 'gameversion'`.

- [ ] **Step 3: Create the module skeleton**

Create `src/gameversion.py`:

```python
"""Game version detection from WoW client executable.

Resolves the addons directory and which expansion the user is on by reading
the PE VS_FIXEDFILEINFO of WoW.exe / Ascension.exe.
"""

import enum
from dataclasses import dataclass
from pathlib import Path

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
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_gameversion.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Run lint and type-check on the new module**

Run:
```bash
uv run ruff check src/gameversion.py tests/test_gameversion.py
uv run mypy src/gameversion.py
```

Expected: no errors.

- [ ] **Step 6: Verification gate**

Hand back to user for review/commit.

---

## Task 3: Implement `_find_game_dir` (walk-up)

**Files:**
- Modify: `src/gameversion.py`
- Modify: `tests/test_gameversion.py`

- [ ] **Step 1: Write failing tests for `_find_game_dir`**

Append to `tests/test_gameversion.py`:

```python
import pytest
from pathlib import Path

from gameversion import _find_game_dir


class TestFindGameDir:
    def test_returns_dir_with_wow_exe(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        assert _find_game_dir(tmp_path) == tmp_path

    def test_returns_dir_with_ascension_exe(self, tmp_path):
        (tmp_path / "Ascension.exe").touch()
        assert _find_game_dir(tmp_path) == tmp_path

    def test_returns_dir_with_both_exes(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        (tmp_path / "Ascension.exe").touch()
        # Either exe is enough to identify the dir; result is the dir itself.
        assert _find_game_dir(tmp_path) == tmp_path

    def test_walks_up_from_nested_dir(self, tmp_path):
        (tmp_path / "WoW.exe").touch()
        nested = tmp_path / "Interface" / "Addons"
        nested.mkdir(parents=True)
        assert _find_game_dir(nested) == tmp_path

    def test_returns_none_when_no_exe_found(self, tmp_path):
        assert _find_game_dir(tmp_path) is None

    def test_walks_up_from_ascension_layout(self, tmp_path):
        # Mimics ...Ascension/Launcher/resources/epoch-live/Ascension.exe
        game_dir = tmp_path / "Launcher" / "resources" / "epoch-live"
        game_dir.mkdir(parents=True)
        (game_dir / "Ascension.exe").touch()
        nested = game_dir / "Interface" / "Addons"
        nested.mkdir(parents=True)
        assert _find_game_dir(nested) == game_dir
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
uv run pytest tests/test_gameversion.py::TestFindGameDir -v
```

Expected: `ImportError: cannot import name '_find_game_dir'`.

- [ ] **Step 3: Implement `_find_game_dir`**

Append to `src/gameversion.py`:

```python
def _find_game_dir(start: Path) -> Path | None:
    """Walk up from `start` (inclusive) toward the filesystem root.
    Return the first directory that contains any of `_EXE_NAMES`,
    or None if no such directory is found.
    """
    current = start
    while True:
        if any((current / name).is_file() for name in _EXE_NAMES):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
uv run pytest tests/test_gameversion.py -v
```

Expected: all tests pass (2 from Task 2 + 6 new = 8 total).

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff check src/gameversion.py tests/test_gameversion.py
uv run mypy src/gameversion.py
```

Expected: no errors.

- [ ] **Step 6: Verification gate**

Hand back to user for review/commit.

---

## Task 4: Implement `_read_expansion_from_exe` (PE parsing via mocks)

**Files:**
- Modify: `src/gameversion.py`
- Modify: `tests/test_gameversion.py`

**Approach note:** Tests mock `pefile.PE` rather than constructing real PE binaries. The mapping logic (major → `Expansion`) is what we test; `pefile`'s correctness is not our concern.

- [ ] **Step 1: Write failing tests for `_read_expansion_from_exe`**

Append to `tests/test_gameversion.py`:

```python
from unittest.mock import MagicMock

from gameversion import GameVersionError, _read_expansion_from_exe


def _make_pe_mock(file_version_ms: int):
    """Build a MagicMock that quacks like a parsed pefile.PE with VS_FIXEDFILEINFO."""
    fixed = MagicMock()
    fixed.FileVersionMS = file_version_ms
    fixed.FileVersionLS = 0
    pe = MagicMock()
    pe.VS_FIXEDFILEINFO = [fixed]
    pe.parse_data_directories = MagicMock()
    return pe


def _ms(major: int, minor: int) -> int:
    return (major << 16) | minor


class TestReadExpansionFromExe:
    def test_wow_exe_vanilla(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(1, 12)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Vanilla

    def test_wow_exe_wotlk(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk

    def test_ascension_exe_wotlk(self, tmp_path, monkeypatch):
        (tmp_path / "Ascension.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk

    def test_ascension_priority_over_wow(self, tmp_path, monkeypatch):
        # Both files exist on disk. The MOCK is parameterised by which path
        # it gets; we verify _read_expansion_from_exe opens Ascension.exe first.
        (tmp_path / "WoW.exe").touch()
        (tmp_path / "Ascension.exe").touch()
        opened: list[str] = []

        def fake_pe(path, *a, **kw):
            opened.append(str(path))
            return _make_pe_mock(_ms(3, 3))

        monkeypatch.setattr("gameversion.pefile.PE", fake_pe)
        assert _read_expansion_from_exe(tmp_path) is Expansion.Wotlk
        assert opened == [str(tmp_path / "Ascension.exe")]

    def test_unsupported_major_tbc_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(2, 4)),
        )
        with pytest.raises(GameVersionError, match=r"unsupported game version 2\."):
            _read_expansion_from_exe(tmp_path)

    def test_no_exe_in_dir_raises(self, tmp_path):
        with pytest.raises(GameVersionError, match=r"no WoW\.exe or Ascension\.exe"):
            _read_expansion_from_exe(tmp_path)

    def test_pefile_failure_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()

        def boom(*a, **kw):
            raise Exception("malformed PE")

        monkeypatch.setattr("gameversion.pefile.PE", boom)
        with pytest.raises(GameVersionError, match=r"could not read version info"):
            _read_expansion_from_exe(tmp_path)

    def test_missing_vs_fixedfileinfo_raises(self, tmp_path, monkeypatch):
        (tmp_path / "WoW.exe").touch()
        pe = MagicMock()
        pe.parse_data_directories = MagicMock()
        # Simulate "no version resource": attribute not present.
        del pe.VS_FIXEDFILEINFO
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)
        with pytest.raises(GameVersionError, match=r"could not read version info"):
            _read_expansion_from_exe(tmp_path)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
uv run pytest tests/test_gameversion.py::TestReadExpansionFromExe -v
```

Expected: `ImportError: cannot import name '_read_expansion_from_exe'`.

- [ ] **Step 3: Implement `_read_expansion_from_exe`**

Edit `src/gameversion.py` — add `import pefile` near the top alongside the existing `import enum`:

```python
import enum
from dataclasses import dataclass
from pathlib import Path

import pefile
```

Then append the function below the existing module contents:

```python
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
    except GameVersionError:
        raise
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
```

Note: `pe.VS_FIXEDFILEINFO` access raises `AttributeError` when the resource is missing — that's caught by the broad `except Exception` and re-raised as `GameVersionError`.

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
uv run pytest tests/test_gameversion.py -v
```

Expected: all `TestReadExpansionFromExe` tests pass plus the earlier 8 = 16 total.

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff check src/gameversion.py tests/test_gameversion.py
uv run mypy src/gameversion.py
```

Expected: no errors. (`pefile` ships type stubs in recent versions; if mypy complains about untyped library, add `# type: ignore[import-untyped]` to the `import pefile` line and re-run.)

- [ ] **Step 6: Verification gate**

Hand back to user for review/commit.

---

## Task 5: Implement `resolve()` (top-level entry point)

**Files:**
- Modify: `src/gameversion.py`
- Modify: `tests/test_gameversion.py`

- [ ] **Step 1: Write failing tests for `resolve`**

Append to `tests/test_gameversion.py`:

```python
from gameversion import Resolved, resolve


class TestResolve:
    # ---- happy paths ----

    def test_walk_up_from_addons_dir(self, tmp_path, monkeypatch):
        # game_dir/WoW.exe exists, cwd is game_dir/Interface/Addons,
        # neither --addons-dir nor --game-version provided.
        game_dir = tmp_path
        (game_dir / "WoW.exe").touch()
        addons_dir = game_dir / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(1, 12)),
        )

        result = resolve(addons_dir_arg=None, game_version_arg=None, cwd=addons_dir)

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Vanilla)

    def test_explicit_addons_dir_derives_game_dir(self, tmp_path, monkeypatch):
        game_dir = tmp_path
        (game_dir / "Ascension.exe").touch()
        addons_dir = game_dir / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: _make_pe_mock(_ms(3, 3)),
        )

        result = resolve(
            addons_dir_arg=str(addons_dir),
            game_version_arg=None,
            cwd=Path("/unrelated"),
        )

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Wotlk)

    def test_game_version_override_skips_exe_read(self, tmp_path, monkeypatch):
        # No exe anywhere on disk, but explicit override is given.
        addons_dir = tmp_path / "Addons"
        addons_dir.mkdir()
        # If we were to try opening any PE, this would blow up:
        monkeypatch.setattr(
            "gameversion.pefile.PE",
            lambda *a, **kw: pytest.fail("pefile.PE must not be called when --game-version overrides"),
        )

        result = resolve(
            addons_dir_arg=str(addons_dir),
            game_version_arg="wotlk",
            cwd=Path("/unrelated"),
        )

        assert result == Resolved(addons_dir=addons_dir, expansion=Expansion.Wotlk)

    # ---- error paths ----

    def test_no_addons_dir_no_walk_up_match_raises(self, tmp_path):
        # cwd has no exe in any parent; no --addons-dir given.
        with pytest.raises(GameVersionError, match=r"could not find game directory"):
            resolve(addons_dir_arg=None, game_version_arg=None, cwd=tmp_path)

    def test_explicit_addons_dir_no_exe_no_override_raises(self, tmp_path):
        # game_dir would be tmp_path/.. — but there's no exe there either.
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        with pytest.raises(GameVersionError, match=r"could not detect game version"):
            resolve(
                addons_dir_arg=str(addons_dir),
                game_version_arg=None,
                cwd=Path("/unrelated"),
            )
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:
```bash
uv run pytest tests/test_gameversion.py::TestResolve -v
```

Expected: `ImportError: cannot import name 'resolve'`.

- [ ] **Step 3: Implement `resolve`**

Append to `src/gameversion.py`:

```python
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
        game_dir: Path | None = addons_dir_path.parent.parent
    else:
        addons_dir_path = None
        game_dir = _find_game_dir(cwd)

    if addons_dir_path is None:
        if game_dir is None:
            raise GameVersionError(
                "could not find game directory: no WoW.exe or Ascension.exe in current "
                "directory or any parent; specify --addons-dir and --game-version"
            )
        addons_dir_path = game_dir / "Interface" / "Addons"

    if game_version_arg is not None:
        expansion = Expansion(game_version_arg)
    else:
        if game_dir is None:
            raise GameVersionError(
                "could not detect game version: no game directory found; "
                "specify --game-version"
            )
        expansion = _read_expansion_from_exe(game_dir)

    return Resolved(addons_dir=addons_dir_path, expansion=expansion)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
uv run pytest tests/test_gameversion.py -v
```

Expected: all tests pass (5 new + 16 prior = 21 total).

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff check src/gameversion.py tests/test_gameversion.py
uv run mypy src/gameversion.py
```

Expected: no errors.

- [ ] **Step 6: Verification gate**

Hand back to user for review/commit.

---

## Task 6: Migrate `toc.find_addons` to take `Expansion`

**Files:**
- Modify: `src/toc.py`
- Modify: `src/snapjaw.py` (callsite + tests pass through `Expansion.Vanilla`)
- Modify: `tests/test_toc.py`
- Modify: `tests/test_integration.py`
- Modify: `tests/test_snapjaw_commands.py` (mock signatures)

**Approach note:** `find_addons`'s signature change is breaking. To keep the suite green, this task atomically updates the function plus all its callers (production + tests). `install_addon` gets a hardcoded `Expansion.Vanilla` here (preserving current behaviour); Task 7 wires it to the user-supplied expansion.

- [ ] **Step 1: Update `tests/test_toc.py` with the new signature and add wotlk cases**

Replace the contents of `tests/test_toc.py` with:

```python
"""Tests for toc.py - .toc file parsing and addon discovery."""

import pytest

from gameversion import Expansion
from toc import find_addons


class TestFindAddons:
    """Tests for finding WoW addons by parsing .toc files."""

    def test_simple_addon(self, make_toc_addon, tmp_path):
        """Single addon with valid Interface version is found."""
        make_toc_addon("MyAddon", 11200)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "MyAddon"

    @pytest.mark.parametrize(
        "version,expansion,expected_count",
        [
            (11200, Expansion.Vanilla, 1),  # vanilla addon found
            (20000, Expansion.Vanilla, 0),  # TBC addon filtered out
            (11201, Expansion.Vanilla, 0),  # version just above max
            (30000, Expansion.Wotlk, 1),    # wotlk lower bound
            (30300, Expansion.Wotlk, 1),    # wotlk upper bound
            (30301, Expansion.Wotlk, 0),    # just above wotlk upper
            (29999, Expansion.Wotlk, 0),    # just below wotlk lower
            (11200, Expansion.Wotlk, 0),    # vanilla TOC under wotlk client
            (30200, Expansion.Vanilla, 0),  # wotlk TOC under vanilla client
        ],
    )
    def test_version_filtering(self, make_toc_addon, tmp_path, version, expansion, expected_count):
        """Addons are filtered based on Interface version + expansion."""
        make_toc_addon("TestAddon", version)
        addons = list(find_addons(str(tmp_path), expansion))
        assert len(addons) == expected_count

    def test_multiple_addons_different_versions(self, make_toc_addon, tmp_path):
        """Only addons within version range are returned."""
        make_toc_addon("VanillaAddon", 11200)
        make_toc_addon("TBCAddon", 20000)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "VanillaAddon"

    def test_no_interface_header(self, tmp_path):
        """Addon without Interface header is skipped."""
        addon_dir = tmp_path / "NoHeader"
        addon_dir.mkdir()
        (addon_dir / "NoHeader.toc").write_text("## Title: NoHeader\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_multiple_addons(self, make_toc_addon, tmp_path):
        """Multiple valid addons are all found."""
        make_toc_addon("AddonA", 11200)
        make_toc_addon("AddonB", 11200)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 2
        names = {a.name for a in addons}
        assert names == {"AddonA", "AddonB"}

    def test_nested_addon_takes_outer(self, make_toc_addon, tmp_path):
        """When addon is nested inside another, only outer addon is returned."""
        outer = make_toc_addon("OuterAddon", 11200)
        inner_dir = outer / "InnerAddon"
        inner_dir.mkdir()
        (inner_dir / "InnerAddon.toc").write_text("## Interface: 11200\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
        assert addons[0].name == "OuterAddon"

    def test_empty_dir(self, tmp_path):
        """Empty directory returns no addons."""
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_toc_case_insensitive(self, tmp_path):
        """Addon with .TOC extension (uppercase) is found."""
        addon_dir = tmp_path / "CaseAddon"
        addon_dir.mkdir()
        (addon_dir / "CaseAddon.TOC").write_text("## Interface: 11200\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1

    @pytest.mark.parametrize(
        "interface_line",
        [
            "## Interface: abc",
            "## Interface: ",
            "## Interface:",
            "##Interface: 11200",  # no space after ##
        ],
    )
    def test_invalid_interface_format_skipped(self, tmp_path, interface_line):
        """Invalid Interface format is skipped."""
        addon_dir = tmp_path / "BadAddon"
        addon_dir.mkdir()
        (addon_dir / "BadAddon.toc").write_text(f"{interface_line}\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 0

    def test_utf8_bom_encoding(self, tmp_path):
        """Addon with UTF-8 BOM encoding is found."""
        addon_dir = tmp_path / "BomAddon"
        addon_dir.mkdir()
        content = b"\xef\xbb\xbf## Interface: 11200\n## Title: BomAddon\n"
        (addon_dir / "BomAddon.toc").write_bytes(content)
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1

    def test_windows_line_endings(self, tmp_path):
        """Addon with Windows line endings (CRLF) is found."""
        addon_dir = tmp_path / "WinAddon"
        addon_dir.mkdir()
        (addon_dir / "WinAddon.toc").write_bytes(b"## Interface: 11200\r\n## Title: WinAddon\r\n")
        addons = list(find_addons(str(tmp_path), Expansion.Vanilla))
        assert len(addons) == 1
```

- [ ] **Step 2: Run the toc tests to verify they fail**

Run:
```bash
uv run pytest tests/test_toc.py -v
```

Expected: `ImportError`/`TypeError` because `find_addons` still takes an `int` and `Expansion` is not used.

- [ ] **Step 3: Update `src/toc.py` to take `Expansion`**

Replace `src/toc.py` with:

```python
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
    match expansion:
        case Expansion.Vanilla:
            return version <= 11200
        case Expansion.Wotlk:
            return 30000 <= version <= 30300


def _get_game_version(toc_path: Path) -> int | None:
    regexp = re.compile(b"## Interface: *(?P<v>[0-9]+)")
    with toc_path.open(mode="rb") as fp:
        for line in fp:
            match = regexp.search(line)
            if match:
                return int(match.groupdict()["v"])
    return None
```

- [ ] **Step 4: Update `install_addon` callsite in `src/snapjaw.py`**

In `src/snapjaw.py`, add an import near the existing `import toc`:

```python
import gameversion
import mygit
import signature
import toc
```

Find the line currently reading:

```python
        addons_by_dir = {item.path: item for item in toc.find_addons(repo.workdir, 11200)}
```

Replace with:

```python
        addons_by_dir = {item.path: item for item in toc.find_addons(repo.workdir, gameversion.Expansion.Vanilla)}
```

(This preserves vanilla-only behaviour; Task 7 plumbs the user-selected expansion through.)

- [ ] **Step 5: Update `tests/test_integration.py`**

In `tests/test_integration.py`, replace each `find_addons(repo.workdir, 11200)` call with `find_addons(repo.workdir, Expansion.Vanilla)` (3 occurrences). Add the import at the top:

```python
from gameversion import Expansion
```

- [ ] **Step 6: Update `tests/test_snapjaw_commands.py` mock signatures**

In `tests/test_snapjaw_commands.py`, find the two places that monkeypatch `snapjaw.toc.find_addons`:

```python
            monkeypatch.setattr("snapjaw.toc.find_addons", lambda workdir, version: iter([]))
```
```python
            monkeypatch.setattr(
                "snapjaw.toc.find_addons", lambda workdir, version: iter([Addon("MyAddon", str(env.repo_dir))])
            )
```

Rename the second positional parameter from `version` to `expansion` in both:

```python
            monkeypatch.setattr("snapjaw.toc.find_addons", lambda workdir, expansion: iter([]))
```
```python
            monkeypatch.setattr(
                "snapjaw.toc.find_addons", lambda workdir, expansion: iter([Addon("MyAddon", str(env.repo_dir))])
            )
```

(Functionally identical — just keeps the test parameter name aligned with the new production signature.)

- [ ] **Step 7: Run the full suite**

Run:
```bash
uv run pytest -q
```

Expected: full pass. The vanilla-only behaviour is preserved end-to-end; the new wotlk filter cases in `test_toc.py` also pass.

- [ ] **Step 8: Lint + type-check**

Run:
```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: no errors.

- [ ] **Step 9: Verification gate**

Hand back to user for review/commit.

---

## Task 7: Wire `--game-version` flag and `gameversion.resolve` into `snapjaw.py`

**Files:**
- Modify: `src/snapjaw.py`
- Modify: `tests/test_snapjaw_helpers.py` (existing `test_wow_dir_auto_detection` may need PE mock)

- [ ] **Step 1: Replace inline walk-up logic with `gameversion.resolve(...)`**

In `src/snapjaw.py`, the current `parse_args()` function contains an inline walk-up block that searches for `WoW.exe`. Replace the block (current lines 82–91 — from `wow_dir = None` through the `addons_dir = wow_dir.joinpath(...)` line) with **nothing** — those lines are deleted. The logic moves to the post-`parse_args()` step below.

Then change the `--addons-dir` argparse declaration to drop the `default=addons_dir` (since auto-detection is no longer done inline):

```python
    parser.add_argument(
        "--addons-dir",
        required=False,
        type=arg_type_dir,
        default=None,
        help="optional path to Interface\\Addons directory",
    )
```

Add the `--game-version` flag immediately below:

```python
    parser.add_argument(
        "--game-version",
        required=False,
        choices=["vanilla", "wotlk"],
        default=None,
        help="override game version detection (vanilla = 1.x, wotlk = 3.3.5)",
    )
```

At the end of `parse_args()`, after `parser.parse_args()` but before `return`, add:

```python
    args = parser.parse_args()
    try:
        resolved = gameversion.resolve(args.addons_dir, args.game_version, Path.cwd())
    except gameversion.GameVersionError as error:
        raise CliError(str(error)) from error
    args.addons_dir = str(resolved.addons_dir)
    args.expansion = resolved.expansion
    return args
```

(Replace the existing `return parser.parse_args()` with the block above.)

Add the `Path` import if not already present:

```python
from pathlib import Path
```

(It is already imported at line 15 of the current file — verify and skip if so.)

- [ ] **Step 2: Update `main()` to surface `CliError` from `parse_args`**

The current `main()` already wraps the callback in a `try/except CliError`. But `parse_args()` is called outside the try. Move it inside:

Current:
```python
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cmd_args = parse_args()
    try:
        cmd_args.callback(cmd_args)
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
```

New:
```python
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        cmd_args = parse_args()
        cmd_args.callback(cmd_args)
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
```

- [ ] **Step 3: Thread `expansion` through `install_addon`**

Change the signature of `install_addon`:

Current:
```python
def install_addon(config: Config, repo_url: str, branch: str | None, addons_dir: str) -> None:
```

New:
```python
def install_addon(config: Config, repo_url: str, branch: str | None, addons_dir: str,
                  expansion: gameversion.Expansion) -> None:
```

Inside the body, replace the hardcoded `gameversion.Expansion.Vanilla` (added in Task 6) with the parameter:

```python
        addons_by_dir = {item.path: item for item in toc.find_addons(repo.workdir, expansion)}
```

Update the two callers in `cmd_install` and `cmd_update`:

In `cmd_install`, change:
```python
    return install_addon(config, repo_url, args.branch or branch_from_url, args.addons_dir)
```
to:
```python
    return install_addon(config, repo_url, args.branch or branch_from_url, args.addons_dir, args.expansion)
```

In `cmd_update`, change:
```python
    for addon in addons:
        install_addon(config, addon.url, addon.branch, args.addons_dir)
```
to:
```python
    for addon in addons:
        install_addon(config, addon.url, addon.branch, args.addons_dir, args.expansion)
```

- [ ] **Step 4: Fix the existing `test_wow_dir_auto_detection`**

The current test in `tests/test_snapjaw_helpers.py` (lines 143–151) creates an empty `WoW.exe` and calls `parse_args()`. With the new code, `parse_args()` calls `gameversion.resolve` which calls `_read_expansion_from_exe` which calls `pefile.PE` — and pefile will choke on an empty file.

Update the test to mock `pefile.PE`:

```python
    def test_wow_dir_auto_detection(self, tmp_path, monkeypatch):
        """WoW directory is auto-detected from current working directory."""
        from unittest.mock import MagicMock

        (tmp_path / "WoW.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        # Mock pefile.PE to report vanilla 1.12.x.
        fixed = MagicMock(FileVersionMS=(1 << 16) | 12, FileVersionLS=0)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "vanilla"
```

- [ ] **Step 5: Run the full suite**

Run:
```bash
uv run pytest -q
```

Expected: full pass.

- [ ] **Step 6: Lint + type-check**

Run:
```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: no errors.

- [ ] **Step 7: Smoke test the CLI**

Run:
```bash
uv run python -m snapjaw --help
```

Expected: help output that includes `--addons-dir` and the new `--game-version {vanilla,wotlk}` flag.

- [ ] **Step 8: Verification gate**

Hand back to user for review/commit.

---

## Task 8: Add CLI tests for new behaviour (Ascension walk-up, override, errors)

**Files:**
- Modify: `tests/test_snapjaw_helpers.py`

- [ ] **Step 1: Add tests for the new CLI scenarios**

Append to the `TestParseArgs`-equivalent class in `tests/test_snapjaw_helpers.py` (the same class that contains `test_wow_dir_auto_detection`):

```python
    def test_ascension_dir_auto_detection(self, tmp_path, monkeypatch):
        """Ascension.exe in game dir is detected and yields wotlk expansion."""
        from unittest.mock import MagicMock

        (tmp_path / "Ascension.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        fixed = MagicMock(FileVersionMS=(3 << 16) | 3, FileVersionLS=(5 << 16) | 12340)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "wotlk"

    def test_game_version_override_flag(self, tmp_path, monkeypatch):
        """--game-version=wotlk overrides exe detection (no exe required)."""
        # Note: --addons-dir is provided so no walk-up is attempted.
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(addons_dir), "--game-version", "wotlk", "status"],
        )

        args = parse_args()
        assert str(args.addons_dir) == str(addons_dir)
        assert args.expansion.value == "wotlk"

    def test_game_version_override_no_exe_required(self, tmp_path, monkeypatch):
        """--game-version overrides also work when no exe exists anywhere."""
        # Empty tmp_path: no game dir, no exes.
        addons_dir = tmp_path / "Addons"
        addons_dir.mkdir()
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr(
            "sys.argv",
            ["snapjaw", "--addons-dir", str(addons_dir), "--game-version", "vanilla", "status"],
        )

        args = parse_args()
        assert args.expansion.value == "vanilla"

    def test_no_exe_no_override_raises_cli_error(self, tmp_path, monkeypatch):
        """No game dir + no override → CliError with actionable message."""
        from snapjaw import CliError

        # Empty tmp_path, no --addons-dir, no --game-version.
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        with pytest.raises(CliError, match=r"could not find game directory"):
            parse_args()

    def test_unsupported_major_raises_cli_error(self, tmp_path, monkeypatch):
        """Exe with unsupported major version (e.g. TBC 2.x) → CliError."""
        from unittest.mock import MagicMock

        from snapjaw import CliError

        (tmp_path / "WoW.exe").touch()
        addons_dir = tmp_path / "Interface" / "Addons"
        addons_dir.mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.cwd", lambda: addons_dir)
        monkeypatch.setattr("sys.argv", ["snapjaw", "status"])

        # 2.4.3 = TBC = unsupported.
        fixed = MagicMock(FileVersionMS=(2 << 16) | 4, FileVersionLS=(3 << 16) | 0)
        pe = MagicMock(VS_FIXEDFILEINFO=[fixed])
        pe.parse_data_directories = MagicMock()
        monkeypatch.setattr("gameversion.pefile.PE", lambda *a, **kw: pe)

        with pytest.raises(CliError, match=r"unsupported game version 2\."):
            parse_args()
```

Make sure the imports at the top of `tests/test_snapjaw_helpers.py` include `pytest`. (Verify by reading the file head; add `import pytest` if missing.)

- [ ] **Step 2: Run the new tests**

Run:
```bash
uv run pytest tests/test_snapjaw_helpers.py -v
```

Expected: all tests pass — both pre-existing and new.

- [ ] **Step 3: Lint**

Run:
```bash
uv run ruff check tests/
```

Expected: no errors.

- [ ] **Step 4: Verification gate**

Hand back to user for review/commit.

---

## Task 9: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Features section**

In `README.md`, find the `## Features` block:

```markdown
## Features
- Support for Git repositories as addon sources
- Detection of outdated and/or modified addons
- Automatic handling of folder naming and nested addon folders
- Fast addon update check due to multithreading implementation
- Simple command line interface
```

Insert a new bullet at the top of the list:

```markdown
## Features
- Supports vanilla (1.12) and WotLK (3.3.5) clients, including custom launchers like Project Ascension (`Ascension.exe`)
- Support for Git repositories as addon sources
- Detection of outdated and/or modified addons
- Automatic handling of folder naming and nested addon folders
- Fast addon update check due to multithreading implementation
- Simple command line interface
```

- [ ] **Step 2: Update the Windows install hint about exe location**

In the Windows install instructions, the current text says "Extract the archive into the WoW folder". Keep that wording — it stays accurate. No change needed to the install steps themselves.

- [ ] **Step 3: Document the `--game-version` override**

After the existing Usage examples block, before the "Requirements for developers" section, add:

```markdown
### Overriding game version detection

snapjaw auto-detects whether you're on vanilla or WotLK by reading
`WoW.exe` or `Ascension.exe` in your game directory. If detection fails
(missing exe, unusual client) you can specify the version explicitly:

```
snapjaw --addons-dir /path/to/Interface/Addons --game-version wotlk status
```

Supported values: `vanilla` (Interface 1.x, Interface ≤ 11200) and
`wotlk` (Interface 3.x, 30000 ≤ Interface ≤ 30300).
```

- [ ] **Step 4: Update the project subtitle if it claims vanilla-only**

The current first line is `# snapjaw: Vanilla World of Warcraft AddOn manager`. Change it to:

```markdown
# snapjaw: World of Warcraft AddOn manager (vanilla and WotLK 3.3.5)
```

- [ ] **Step 5: Verification gate**

Render the README locally if convenient (any markdown viewer) to spot-check formatting. Hand back to user for review/commit.

---

## Task 10: Full verification pass

**Files:** none changed. Verification only.

- [ ] **Step 1: Full test suite**

Run:
```bash
uv run pytest -q
```

Expected: all tests pass. (Compared to baseline before this plan: same number of pre-existing tests still green, plus the new gameversion + wotlk + CLI tests.)

- [ ] **Step 2: Strict lint**

Run:
```bash
uv run ruff check src/ tests/
```

Expected: no errors. (The project already enforces `select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]` in `pyproject.toml`.)

- [ ] **Step 3: Type check**

Run:
```bash
uv run mypy src/
```

Expected: no errors. If `pefile` is reported as untyped, the `# type: ignore[import-untyped]` from Task 4 keeps mypy quiet.

- [ ] **Step 4: Smoke-test the binary build (Linux)**

Run:
```bash
uv run python -m snapjaw --help
```

Expected: help text shows both `--addons-dir` and `--game-version`.

- [ ] **Step 5: Verification gate**

If anything fails in any of the above steps — fix it before declaring this task done. Hand back to user for review/commit. The final commit (or commit batch) closes out the WotLK-support feature.

---

## Spec coverage check (self-review for plan author)

| Spec section / decision | Implemented in |
|---|---|
| `pefile` dependency added without manual pin | Task 1 |
| `Expansion` enum (`Vanilla`, `Wotlk`) | Task 2 |
| `_MAJOR_TO_EXPANSION = {1: Vanilla, 3: Wotlk}` | Task 2 |
| `_EXE_NAMES = ("Ascension.exe", "WoW.exe")` (priority order) | Task 2 |
| `GameVersionError`, `Resolved` dataclass | Task 2 |
| `_find_game_dir`: walk-up, both/either/neither exe | Task 3 |
| `_read_expansion_from_exe`: PE read + Ascension priority | Task 4 |
| Error: missing exe, missing VS_FIXEDFILEINFO, unsupported major | Task 4 (tests + impl) |
| `resolve`: addons_dir derivation rules + override semantics | Task 5 |
| Error: walk-up failure with no override → "could not find game directory" | Task 5 |
| Error: derived game_dir has no exe → "could not detect game version" | Task 5 (via `_read_expansion_from_exe`) |
| `_interface_matches`: vanilla `<= 11200`, wotlk `30000–30300` | Task 6 |
| `find_addons` signature change (int → `Expansion`) | Task 6 |
| `--game-version=vanilla|wotlk` CLI flag | Task 7 |
| Walk-up replacement; exe untouched when override given | Task 7 |
| `install_addon` plumbed with `expansion` | Task 7 |
| Tests: vanilla unchanged + new wotlk boundary cases | Task 6 |
| Tests: Ascension walk-up + override + error messages | Tasks 4, 8 |
| README updated (features, supported clients, override flag) | Task 9 |
| Lint + type check + full suite green on Linux + Windows | Task 10 |

No spec section without a corresponding task.

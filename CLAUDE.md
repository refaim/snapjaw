# snapjaw — Developer Guide

## Quality Gates

Before declaring a task done, run:

    uv run pytest -q
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/
    uv run mypy src/

All four must pass clean. `ruff format --check` is independent of
`ruff check` — the linter does not enforce formatting and the formatter
does not lint. CI runs both. If `ruff format --check` reports
differences, run `uv run ruff format src/ tests/` to fix them.

The project's CI runs the same checks on Linux and Windows; if any of
them fails on either OS, treat as a blocker.

## Workflow Rules

- **TDD**: write tests before implementation code, always.
- **No intermediate commits during plan execution.** Work the task to
  completion; the user commits when they review and approve. Never run
  `git commit` (or any publishing action: `push`, PR, merge) without
  an explicit user request, even if a skill prescribes committing as
  part of its checklist.
- **Verification before completion.** Don't claim a task is done until
  the full quality gates above pass. Evidence (command output) before
  assertion.

## Agent & Subagent Rules

These rules override any conflicting defaults or skills (including
superpowers). Apply whenever you are executing work or dispatching a
subagent.

- **Opus only.** Every subagent spawn passes `model: "opus"`. No
  Sonnet, no Haiku, even for cheap jobs like file surveys. If a skill
  default picks another model, override it.
- **Parallelise by default.** Independent work — unrelated surveys,
  non-conflicting edits, research across separate modules — goes out
  as multiple agents in one message. Serial dispatch is only for
  genuine data dependencies.
- **No worktrees.** Work directly in the main checkout. Skip any skill
  step that suggests creating a git worktree, even when the skill
  names it as mandatory.
- **TDD, strict and unconditional.** Failing test before production
  code, for every feature and every bugfix. No exceptions for "too
  small" or "will add later".
- **100% coverage on all new or touched code — lines AND branches.**
  Uncovered branches block completion. Measure before claiming done.
- **Review loops to zero.** After implementation, dispatch a separate
  code-reviewer agent (never self-review). Address every comment.
  Re-dispatch review after fixes. Repeat until the reviewer returns
  zero comments. Only zero-comment review closes the task.

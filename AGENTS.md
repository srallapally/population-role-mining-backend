# AGENTS.md

## Scope

These instructions apply to this Python project.

## Working agreements

- Keep changes surgical and limited to the requested task.
- State assumptions before making code changes.
- Do not introduce new dependencies unless explicitly requested.
- Prefer simple, readable Python over unnecessary abstractions.
- Match the existing project style and naming conventions.
- Do not reformat unrelated files.

## Python environment

- Use the project's existing environment and dependency manager.
- Prefer the existing lockfile/tooling:
  - `uv.lock` -> use `uv`
  - `poetry.lock` -> use `poetry`
  - `requirements.txt` -> use `pip`
  - `pyproject.toml` only -> inspect configured tooling before choosing commands
- Do not change Python versions unless explicitly requested.

## Before editing

- Inspect the relevant files first.
- Identify the smallest change that satisfies the request.
- For bug fixes, first look for an existing test or create a focused regression test when practical.

## Testing

Run the narrowest relevant test first.

Common commands, depending on the project:

```bash
pytest
pytest path/to/test_file.py
python -m pytest
```

If the project uses these tools, run them only when relevant to touched files:

```bash
ruff check .
ruff format --check .
mypy .
```

Do not claim the change is complete unless the relevant tests/checks pass, or explicitly state what could not be run.

## Code review priorities

When reviewing code, prioritize:

1. Correctness
2. Security
3. Data loss or migration risk
4. Test coverage
5. Maintainability
6. Style

Separate showstoppers from non-blocking suggestions.

## Python style

- Use type hints when the surrounding code already uses them.
- Avoid broad `except Exception` unless the existing codebase uses that pattern and there is a clear reason.
- Avoid mutable default arguments.
- Prefer pathlib for new filesystem code unless the existing file uses `os.path`.
- Keep functions small, but do not create abstractions for one-off logic.
- Preserve existing public APIs unless explicitly asked to change them.

## Files not to touch without explicit request

- Generated files
- Lockfiles
- Large formatting-only changes
- `.idea/` PyCharm project files
- Migration files
- Vendored dependencies

## Planning protocol

When the user says `PLAN`, `PLAN ONLY`, or `NO CODE YET`, Codex must operate in planning mode.

In planning mode:

- Do not edit files.
- Do not create files.
- Do not run formatters, migrations, generators, or destructive commands.
- You may inspect/read files and explain findings.
- Produce a plan with:
  1. Assumptions
  2. Ambiguities or questions
  3. Proposed changes
  4. Files likely to be touched
  5. Tests/checks to run
  6. Risks
- Stop after the plan and wait for explicit approval.

Implementation may begin only when the user says one of:

- `IMPLEMENT`
- `PROCEED`
- `APPLY THE PLAN`
- `MAKE THE CHANGE`

## Protected environment and secrets files

Codex must treat local environment, credential, and secret files as protected.

Never create, edit, stage, commit, merge, rebase, resolve conflicts in, print, summarize, or include in patches/PRs any of the following:

- `.env`
- `.env.*`
- `*.env`
- `.flaskenv`
- `.envrc`
- `local_settings.py`
- `settings.local.py`
- `secrets.py`
- `secrets.toml`
- `.streamlit/secrets.toml`
- `.venv/`
- `venv/`
- `env/`

If a task requires a new environment variable:

- Do not modify `.env`.
- Update `.env.example`, `.env.sample`, or project documentation instead.
- Use placeholder values only, for example `API_KEY=replace-me`.
- Never invent or expose real secrets.

If a merge, rebase, or patch operation touches one of these protected files:

- Stop immediately.
- Report which protected file would be affected.
- Ask for explicit user approval before proceeding.

Before claiming completion, verify that protected files are not included in the change set:

```bash
git diff --name-only
git status --short
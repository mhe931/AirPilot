# Contributing

AirPilot is early-stage and safety-sensitive because it can move and click the
real Windows pointer.

Before opening a PR:

```powershell
uv sync --extra dev
uv run --extra dev ruff format --check .
uv run --extra dev ruff check .
uv run --extra dev mypy src
uv run --extra dev python -m pytest
```

Guidelines:

- Keep platform-independent gesture logic in `src/airpilot/domain`.
- Keep real OS input behind injectable adapters.
- Add synthetic landmark tests for gesture behavior.
- Do not commit camera frames, recordings, secrets, build artifacts, or virtual
  environments.
- Document user-visible behavior changes in `README.md` and
  `docs/PROJECT_STATUS.md`.

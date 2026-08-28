# Goal Summary: Help layout, transparency, and custom shortcuts

## What was achieved

- Help content now separates Intro/safety/quick-start text into a wrapped panel
  above the gesture/action table, leaving table rows for registered gestures and
  actions.
- Help table layout was widened for gesture descriptions, remains resizable, and
  has focused tests covering coverage, wrapping, row sizing, and no default
  truncation.
- Main preview rendering now uses separate overlay/status, sidebar/dashboard, and
  preview regions with opacity applied only to region backgrounds.
- Settings now provides independent overlay/status and sidebar/dashboard
  background opacity controls with bounded persistence and migration to schema
  version 13.
- Custom gesture shortcuts now preserve and execute recorded shortcut keys such
  as `Ctrl+9`; internal binding IDs such as `go_last_tab` remain labels only and
  are never emitted as keyboard actions.
- Runtime Apply refresh updates gesture bindings in-place so Help, dashboard,
  matcher, and dispatcher use new bindings without restarting.

## Iteration history

- Iteration 1: Builder implemented the fixes and focused coverage. Inspector
  passed the implementation after independent code review and quality gates.

## Inspector findings and resolution

- Inspector found no blocking issues.
- Inspector verified the critical custom-shortcut path dispatches recorded keys,
  opacity migration/defaults are present, Help Intro rows are excluded from the
  table, and quality gates pass.

## Validation evidence

- `uv run --extra dev ruff format --check .`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev python -m pytest` — 366 passed, 1 skipped
- `uv sync --extra package`
- `powershell -ExecutionPolicy Bypass -File scripts\package_windows.ps1`
- `dist\AirPilot\AirPilot.exe --list-cameras` — detected `Camera 0`
- `uv run --extra dev airpilot --camera 0 --diagnose-seconds 5` —
  completed with `AirPilot exit reason: diagnostics_complete`

## Recommendations

- Continue manual live validation for gesture feel, actual Help readability, and
  long-run camera stability because those remain hardware/operator-dependent.
- Consider adding an automated visual snapshot harness for the native OpenCV/Tk
  windows if future UI layout work continues to grow.

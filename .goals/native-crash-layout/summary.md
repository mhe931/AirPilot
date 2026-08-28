# Goal Summary: Native crash and main-window overlap

## What was achieved

- Diagnosed the reproducible Windows native crash around the main OpenCV event
  loop and documented the relevant `main()`/`run()` call sites.
- Enabled process-level crash evidence with `faulthandler` and added
  thread-aware runtime stress tools.
- Hardened lifecycle ownership so camera and MediaPipe tracker objects are used
  on one owner thread, tracker calls are serialized structurally, invalid frames
  are rejected before MediaPipe `process()`, and shutdown remains ordered and
  idempotent.
- Investigated the MediaPipe `NORM_RECT` warning and added guards/tests so
  AirPilot does not send empty or zero-dimension frames into MediaPipe.
- Added a privacy-safe minimal camera+MediaPipe stress reproducer that stores
  only textual summaries, never frames.
- Fixed the main-window overlap by reserving sidebar width and positioning
  overlay/FPS/score/help/settings/quit text inside the visible camera region.
- Preserved separate sidebar/overlay background opacity behavior while keeping
  text fully opaque.

## Iteration history

- Iteration 1: Implemented the initial GIL/lifecycle and layout fix, but
  Inspector failed it for missing stress evidence and missing minimal reproducer.
- Iteration 2: Added the camera+MediaPipe stress tool, invalid-frame guards,
  owner-thread assertions, dependency evidence, and 30-cycle/5-minute stress
  artifacts. Inspector failed it for missing 15-minute and UI lifecycle stress
  evidence.
- Iteration 3: Added the 15-minute continuous camera+MediaPipe artifact and UI
  lifecycle stress coverage/substitutes. Inspector passed the technical and
  stress criteria.

## Validation evidence

- 30 repeated camera+MediaPipe start/stop cycles passed with 0 crashes.
- 15-minute continuous camera+MediaPipe run processed 8975 frames over 900.46s
  with 0 crashes and 0 tracking errors.
- UI lifecycle stress ran 8 suites x 30 cycles with 0 errors, covering Help,
  Settings, Tk root lifecycle, key handling, UI action dispatch, pause/resume,
  arm/disarm, and shortcut-mode baseline.
- Full automated gates passed: `ruff format --check`, `ruff check`, `mypy src`,
  and `pytest` with 578 passed and 5 skipped.
- Packaging and packaged smoke passed, including packaged `--list-cameras` and
  packaged diagnostics.
- Inspector independently verified layout geometry assertions, no frame storage,
  stress artifacts, and quality gates.

## Recommendations

- Run the documented manual hardware procedures when convenient for physical
  camera interruption, live gesture/title-bar exits, and subjective long-run UI
  readability, because those depend on local display and operator interaction.
- Keep the stress tools in CI-adjacent use for future MediaPipe/OpenCV/Tk
  lifecycle changes.

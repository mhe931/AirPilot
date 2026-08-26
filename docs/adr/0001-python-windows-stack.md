# ADR 0001: Python Windows Stack

## Status

Accepted

## Context

Phase 1 needs a fast path to webcam capture, robust hand landmarks, Windows
mouse control, tests, and packaging.

Current official documentation shows MediaPipe's Python hand landmarker supports
hand-landmark detection and video/live-stream modes. PyInstaller remains the
practical package bundler for Python desktop apps on Windows.

## Decision

Use Python 3.11 with:

- OpenCV for webcam capture and preview.
- MediaPipe for hand tracking.
- PyAutoGUI for Windows mouse control and corner failsafe.
- `uv` for dependency locking and command execution.
- Ruff, mypy, and pytest for quality gates.
- PyInstaller for initial Windows packaging.

## Consequences

- The first Windows implementation can be functional and testable quickly.
- Packaging includes large binary CV dependencies.
- Lower-level Windows `SendInput` can replace PyAutoGUI later behind the same
  `MouseController` interface if precision or policy requires it.

## Sources

- MediaPipe Python hand landmarks:
  https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python
- PyInstaller installation:
  https://pyinstaller.org/en/stable/installation.html
- PyInstaller PyPI project:
  https://pypi.org/project/pyinstaller/

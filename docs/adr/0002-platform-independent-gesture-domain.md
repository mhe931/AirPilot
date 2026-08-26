# ADR 0002: Platform-Independent Gesture Domain

## Status

Accepted

## Context

AirPilot needs Windows functionality now and Android reuse later. Platform APIs
for camera, pointer control, and UI differ substantially.

## Decision

Keep normalized landmarks, cursor mapping, and gesture state in
`src/airpilot/domain`. Adapters convert platform-specific camera/tracker/input
data at the edges.

## Consequences

- Gesture rules can be tested with synthetic landmarks.
- Windows input can be replaced or hardened without rewriting gesture logic.
- Android can reuse concepts while mapping events to AccessibilityService/IME
  APIs instead of mouse injection.

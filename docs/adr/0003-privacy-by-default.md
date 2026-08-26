# ADR 0003: Privacy By Default

## Status

Accepted

## Context

AirPilot uses a live camera and may eventually interact with screen contents.
User trust depends on clear boundaries.

## Decision

Process frames locally by default. Do not record, upload, persist, or log camera
frames. Do not add telemetry without opt-in design and documentation.

## Consequences

- The app can be used offline after dependencies are installed.
- Tests use synthetic landmarks instead of saved user video.
- Future debugging tools must redact or avoid sensitive visual data by design.

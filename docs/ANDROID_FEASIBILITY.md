# Android Feasibility

## Bottom Line

Android is feasible as a user-enabled assistive controller, not as unrestricted
OS-level pointer injection. Third-party apps cannot generally inject arbitrary
touch or key events into every app. The realistic path is an
AccessibilityService-driven controller with foreground camera processing.

## Platform Limitations

- There is no public third-party system mouse-driver API for camera gestures.
- Android's hidden `INJECT_EVENTS` permission is signature-level and not
  available to ordinary apps.
- Instrumentation-based pointer injection is scoped to the tested/instrumented
  app, not all apps.
- Accessibility gestures are coordinate taps/swipes/drags, not a true hover
  cursor.
- Secure surfaces, lock screen flows, banking/payment apps, overlay-blocking
  windows, and some system UI surfaces may limit interaction.
- Android 14+ restricts starting camera foreground services while backgrounded.

## Feasible Mechanisms

- `AccessibilityService`: primary mechanism. Use declared gesture capability,
  `dispatchGesture()` for taps/swipes/drags, node actions for clickable UI, and
  global actions where available.
- `InputMethodService`: optional text entry path once the user selects AirPilot
  as an input method.
- CameraX: foreground camera pipeline with on-device frame processing.
- Overlay cursor: optional visual feedback through `SYSTEM_ALERT_WINDOW`, with
  explicit grant and tapjacking-aware design.

## Samsung Galaxy S24 Ultra Notes

- Treat the S24 Ultra as a modern 64-bit Samsung Android device with current
  privacy indicators and foreground-service restrictions.
- S Pen Remote/Air Actions can complement foreground app interactions, but
  Samsung documents them as foreground-activity listener events, not a global
  system controller path.

## Permissions, Privacy, And Security

- Request `CAMERA` only when needed.
- If background camera is introduced, declare the camera foreground-service type
  and design around Android 14+ while-in-use restrictions.
- Accessibility requires `BIND_ACCESSIBILITY_SERVICE` and explicit user enablement
  in Settings.
- Minimize accessibility event scope. Do not collect screen text, passwords, or
  camera frames by default.
- Make overlay feedback non-deceptive and easy to disable.

## Play Store Implications

Google Play allows Accessibility API use only when it is narrow, disclosed, and
appropriate. AirPilot should remain deterministic and user-command-driven. It
must not autonomously initiate, plan, or execute user actions.

Only declare `isAccessibilityTool=true` if the Android product is genuinely
positioned and implemented as an accessibility tool for users with disabilities;
otherwise use prominent disclosure and consent.

## Recommended Android Path

Build a foreground Android prototype:

```text
CameraX -> on-device hand landmarks -> shared gesture rules -> AccessibilityService actions
                                        -> optional overlay pointer
                                        -> optional IME for text
```

Validate on a Samsung Galaxy S24 Ultra before Play distribution planning.

## Sources

- Android AccessibilityService guide:
  https://developer.android.com/guide/topics/ui/accessibility/service
- GestureDescription API:
  https://developer.android.com/reference/android/accessibilityservice/GestureDescription
- Android `INJECT_EVENTS` AOSP manifest:
  https://android.googlesource.com/platform/frameworks/base/+/master/core/res/AndroidManifest.xml
- Foreground service types:
  https://developer.android.com/develop/background-work/services/fgs/service-types
- Android runtime permissions:
  https://developer.android.com/training/permissions/requesting
- CameraX overview:
  https://developer.android.com/media/camera/camerax
- Android tapjacking guidance:
  https://developer.android.com/privacy-and-security/risks/tapjacking
- Play Accessibility API policy:
  https://support.google.com/googleplay/android-developer/answer/10964491
- Play sensitive permissions policy:
  https://support.google.com/googleplay/android-developer/answer/16558241
- Samsung S Pen Remote SDK:
  https://developer.samsung.com/galaxy-spen-remote/s-pen-remote-sdk.html
- Samsung Air Actions:
  https://developer.samsung.com/galaxy-spen-remote/air-actions.html
- Samsung S Pen FAQ:
  https://developer.samsung.com/galaxy-spen-remote/faq.html
- Samsung 64-bit device support note:
  https://docs.samsungknox.com/dev/knox-sdk/kbas/kba-1150-sunsetting-32-bit-app-support-on-samsung-devices/

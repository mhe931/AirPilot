from airpilot.cursor_feedback import NoOpCursorFeedback, WindowsCursorFeedback


def test_noop_cursor_feedback_restores_inactive_state() -> None:
    feedback = NoOpCursorFeedback()

    feedback.set_control_active(True)
    assert feedback.active is True

    feedback.restore()
    assert feedback.active is False


def test_windows_cursor_feedback_reapplies_transient_active_cursor() -> None:
    calls: list[int] = []

    class FakeUser32:
        def LoadCursorW(self, _module: None, cursor_id: int) -> int:
            return cursor_id

        def SetCursor(self, cursor: int) -> None:
            calls.append(cursor)

    feedback = object.__new__(WindowsCursorFeedback)
    feedback._user32 = FakeUser32()
    feedback._hand = 32649
    feedback._arrow = 32512
    feedback._active = False

    feedback.set_control_active(True)
    feedback.set_control_active(True)
    feedback.set_control_active(False)

    assert calls == [32649, 32649, 32512]

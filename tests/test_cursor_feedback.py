from airpilot.cursor_feedback import NoOpCursorFeedback, create_cursor_feedback


def test_noop_cursor_feedback_restores_inactive_state() -> None:
    feedback = NoOpCursorFeedback()

    feedback.set_control_active(True)
    assert feedback.active is False

    feedback.restore()
    assert feedback.active is False


def test_cursor_feedback_factory_does_not_override_os_cursor_icon() -> None:
    feedback = create_cursor_feedback()

    assert isinstance(feedback, NoOpCursorFeedback)
    feedback.set_control_active(True)
    assert feedback.active is False
    feedback.restore()
    assert feedback.active is False

from airpilot.display import VirtualDesktop, WindowsDisplayProvider


def test_windows_display_provider_reads_virtual_desktop_metrics() -> None:
    calls: list[int] = []

    class FakeUser32:
        values = {
            76: -1280,
            77: -200,
            78: 3200,
            79: 1280,
        }

        def GetSystemMetrics(self, metric: int) -> int:
            calls.append(metric)
            return self.values[metric]

    provider = object.__new__(WindowsDisplayProvider)
    provider._user32 = FakeUser32()

    assert provider.virtual_desktop() == VirtualDesktop(
        left=-1280,
        top=-200,
        width=3200,
        height=1280,
    )
    assert calls == [76, 77, 78, 79]

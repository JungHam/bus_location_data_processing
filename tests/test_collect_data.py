from datetime import datetime, timedelta
from unittest.mock import Mock

import collect_data

SLOT = datetime(2026, 10, 13, 8, 0)


class TestNextSlotAfter:
    def test_normal_case_is_the_next_interval(self):
        assert collect_data.next_slot_after(SLOT, datetime(2026, 10, 13, 8, 0, 20)) == datetime(
            2026, 10, 13, 8, 10
        )

    def test_overrun_skips_to_current_slot_instead_of_catching_up(self):
        assert collect_data.next_slot_after(SLOT, datetime(2026, 10, 13, 8, 23)) == datetime(
            2026, 10, 13, 8, 20
        )


class TestCollectOnce:
    def test_one_route_failure_does_not_stop_the_others(self, monkeypatch):
        monkeypatch.setattr(collect_data, "ROUTE_IDS", ["R1", "R2", "R3"])
        save = Mock(side_effect=[KeyError("response"), "path2", "path3"])
        monkeypatch.setattr(collect_data, "save_bus_location", save)

        collect_data.collect_once(SLOT)

        assert save.call_count == 3

    def test_every_route_is_saved_under_the_same_slot(self, monkeypatch):
        monkeypatch.setattr(collect_data, "ROUTE_IDS", ["R1", "R2"])
        save = Mock(return_value="path")
        monkeypatch.setattr(collect_data, "save_bus_location", save)

        collect_data.collect_once(SLOT)

        assert [call.args[2] for call in save.call_args_list] == [SLOT, SLOT]


class TestRun:
    def test_early_wakeup_does_not_relabel_slots(self, monkeypatch):
        """sleep이 경계보다 일찍 깨어나도 각 구간이 정확히 한 번, 올바른 키로 수집된다."""

        class FakeClock:
            def __init__(self, start):
                self.t = start

            def now(self):
                return self.t

            def sleep(self, seconds):
                # 긴 대기는 0.5초 일찍 깨어난다 (경계 직전 기상을 재현)
                self.t += timedelta(seconds=seconds - 0.5 if seconds > 1 else seconds)

        clock = FakeClock(datetime(2026, 10, 13, 7, 50, 13))
        slots = []
        monkeypatch.setattr(collect_data, "collect_once", slots.append)

        collect_data.run(max_slots=3, now_fn=clock.now, sleep_fn=clock.sleep)

        assert slots == [
            datetime(2026, 10, 13, 7, 50),
            datetime(2026, 10, 13, 8, 0),
            datetime(2026, 10, 13, 8, 10),
        ]

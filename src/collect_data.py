import logging
import time
from datetime import datetime, timedelta
from typing import Callable

from bus_api import COLLECT_INTERVAL_MINUTES, logical_slot, save_bus_location

CITY_CODE = 21
# 2023-07-31 승하차 통계 상위 노선 중 지역·길이가 다른 5개 (68·81·31·115-1·24)
ROUTE_IDS = [
    "BSB5200068000",
    "BSB5200081000",
    "BSB5200031000",
    "BSB5200115100",
    "BSB5200024000",
]

logger = logging.getLogger(__name__)


def collect_once(slot: datetime) -> None:
    for route_id in ROUTE_IDS:
        try:
            out_path = save_bus_location(CITY_CODE, route_id, slot)
        except Exception:
            logger.exception("Collection failed for routeId=%s slot=%s", route_id, slot)
            continue
        if out_path:
            logger.info("Saved %s", out_path)


def next_slot_after(slot: datetime, now: datetime) -> datetime:
    """다음에 수집할 구간. 수집이 길어져 다음 구간을 넘겼다면 건너뛰고 지금 구간으로 간다."""
    return max(slot + timedelta(minutes=COLLECT_INTERVAL_MINUTES), logical_slot(now))


def wait_until(
    target: datetime,
    now_fn: Callable[[], datetime] = datetime.now,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """target 시각이 될 때까지 기다린다. sleep이 일찍 깨어도 target 전에는 돌려보내지 않는다."""
    while True:
        remaining = (target - now_fn()).total_seconds()
        if remaining <= 0:
            return
        sleep_fn(remaining)


def run(
    max_slots: int | None = None,
    now_fn: Callable[[], datetime] = datetime.now,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """구간마다 수집을 반복한다. max_slots를 주면 그 횟수만큼만 돌고 끝난다(테스트용)."""
    # 구간은 깨어난 시각에서 다시 계산하지 않고 예정된 값을 그대로 쓴다.
    # (경계 직전에 깨어나면 직전 구간 키를 덮어쓰고 이번 구간을 건너뛰게 된다)
    slot = logical_slot(now_fn())
    collected = 0
    while True:
        collect_once(slot)
        collected += 1
        if max_slots is not None and collected >= max_slots:
            return
        slot = next_slot_after(slot, now_fn())
        wait_until(slot, now_fn, sleep_fn)

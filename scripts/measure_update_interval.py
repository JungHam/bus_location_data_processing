"""TAGO 버스 위치 데이터의 갱신 주기와 호출 품질을 측정한다.

같은 노선을 일정 간격으로 반복 호출해 차량(vehicleno)별 좌표가 바뀌는 간격,
응답 시간, 재시도 횟수를 집계한다. 측정 해상도는 --interval 값이다.

사용 예: python scripts/measure_update_interval.py --interval 5 --duration 600
"""
import argparse
import csv
import logging
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import bus_api  # noqa: E402
from secrets_mask import mask_service_key  # noqa: E402

OUTPUT_DIR = "data/measure"


class RetryCounter(logging.Handler):
    """bus_api가 남기는 재시도 WARNING 로그를 세어 호출별 재시도 횟수를 얻는다."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("Retry "):
            self.count += 1


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def poll(
    city_code: int, route_id: str, counter: RetryCounter
) -> tuple[list[dict], float, int, str]:
    """(버스 목록, 응답 시간, 재시도 횟수, 오류 종류)를 돌려준다. 오류가 없으면 종류는 빈 문자열."""
    retries_before = counter.count
    error = ""
    started = time.monotonic()
    try:
        buses = bus_api.get_bus_location_by_route(city_code, route_id)
    except Exception as e:  # 측정은 실패해도 계속 진행하고 실패로 기록한다
        error = mask_service_key(f"{type(e).__name__}: {e}")
        logging.getLogger(__name__).error("poll failed: %s", error)
        buses = []
        error = error[:120]
    elapsed = time.monotonic() - started
    return buses, elapsed, counter.count - retries_before, error


def summarize(change_intervals: list[float], latencies: list[float], polls: list[dict]) -> None:
    total = len(polls)
    errors = [p["error"] for p in polls if p["error"]]
    empty = sum(1 for p in polls if p["buses"] == 0 and not p["error"])
    with_retry = sum(1 for p in polls if p["retries"] > 0)
    print(f"\n호출 {total}회 / 예외 {len(errors)}회 / 빈 응답(예외 없이, 재시도 후에도) {empty}회 / 재시도 발생 {with_retry}회")
    for message, count in Counter(errors).most_common():
        print(f"  예외 {count}회: {message}")
    print(f"재시도 합계 {sum(p['retries'] for p in polls)}회")
    if latencies:
        print(
            f"응답 시간(재시도 포함) p50={percentile(latencies, 50):.2f}s "
            f"p95={percentile(latencies, 95):.2f}s"
        )
    if change_intervals:
        print(
            f"좌표 변경 간격 {len(change_intervals)}건: "
            f"min={min(change_intervals):.1f}s p10={percentile(change_intervals, 10):.1f}s "
            f"median={statistics.median(change_intervals):.1f}s "
            f"p90={percentile(change_intervals, 90):.1f}s"
        )
        print("※ 정차·정체로 좌표가 안 바뀐 구간은 간격이 늘어나므로 min/p10이 갱신 주기에 가깝다.")
    else:
        print("좌표 변경이 관측되지 않았다. 호출 간격을 늘리거나 측정 시간을 늘려 볼 것.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--city-code", type=int, default=21)
    parser.add_argument("--route-id", default="BSB5200002000")
    parser.add_argument("--interval", type=float, default=5.0, help="호출 간격(초)")
    parser.add_argument("--duration", type=float, default=600.0, help="총 측정 시간(초)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    counter = RetryCounter()
    logging.getLogger("bus_api").addHandler(counter)

    last_position: dict[str, tuple] = {}
    last_change_at: dict[str, float] = {}
    change_intervals: list[float] = []
    latencies: list[float] = []
    polls: list[dict] = []

    out_path = os.path.join(OUTPUT_DIR, f"poll_{datetime.now():%Y%m%d_%H%M%S}.csv")
    start = time.monotonic()
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_s", "buses", "latency_s", "retries", "changed_vehicles", "error"])

        next_tick = 0.0
        while next_tick < args.duration:
            observed_at = time.monotonic() - start  # 응답 지연이 간격에 섞이지 않도록 호출 직전에 찍는다
            buses, latency, retries, error = poll(args.city_code, args.route_id, counter)

            changed = 0
            for bus in buses:
                vehicle = bus.get("vehicleno")
                position = (bus.get("gpslati"), bus.get("gpslong"))
                if vehicle in last_position and last_position[vehicle] != position:
                    changed += 1
                    # 첫 변경은 직전 변경 시점을 모르므로 간격 계산에서 제외한다
                    if vehicle in last_change_at:
                        change_intervals.append(observed_at - last_change_at[vehicle])
                    last_change_at[vehicle] = observed_at
                last_position[vehicle] = position

            latencies.append(latency)
            polls.append({"buses": len(buses), "retries": retries, "error": error})
            writer.writerow([f"{observed_at:.1f}", len(buses), f"{latency:.2f}", retries, changed, error])
            f.flush()
            print(f"[{observed_at:6.1f}s] buses={len(buses)} changed={changed} "
                  f"latency={latency:.2f}s retries={retries}" + (f" ERROR={error}" if error else ""))

            next_tick += args.interval
            time.sleep(max(0.0, next_tick - (time.monotonic() - start)))

    print(f"\n원시 기록: {out_path}")
    summarize(change_intervals, latencies, polls)


if __name__ == "__main__":
    main()

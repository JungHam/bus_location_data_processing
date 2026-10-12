"""저장된 raw 파일에서 노선별·수집 구간별 운행 차량 수를 보여준다.

사용 예: python scripts/count_vehicles.py --date 2026-10-13 --from-hour 7 --to-hour 9
raw 파일에는 응답의 items만 저장되므로, 차량 수는 파일 안 레코드 수다(totalCount는 저장하지 않는다).
수집 중 누락이 있었는지는 logs/collector.out의 "Truncated response" 경고로 확인한다.
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict

RAW_DIR = "data/raw/bus_location"
FILE_PATTERN = re.compile(r"^(?P<route>.+)_(?P<slot>\d{12})\.json$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--from-hour", type=int, default=0)
    parser.add_argument("--to-hour", type=int, default=23)
    args = parser.parse_args()

    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for hour in range(args.from_hour, args.to_hour + 1):
        pattern = os.path.join(RAW_DIR, f"dt={args.date}", f"hour={hour:02d}", "*.json")
        for path in sorted(glob.glob(pattern)):
            match = FILE_PATTERN.match(os.path.basename(path))
            if not match:
                continue
            with open(path, encoding="utf-8") as f:
                counts[match["slot"][8:]][match["route"]] = len(json.load(f))

    if not counts:
        print("해당 조건의 raw 파일이 없다.")
        return

    routes = sorted({r for by_route in counts.values() for r in by_route})
    print("구간(HHMM) " + " ".join(f"{r[-7:]:>8}" for r in routes) + "   합계")
    for slot in sorted(counts):
        row = [counts[slot].get(r) for r in routes]
        cells = " ".join(f"{'-' if v is None else v:>8}" for v in row)
        print(f"{slot:>10} {cells} {sum(v or 0 for v in row):>6}")

    print("\n노선별 최대 차량 수 (numOfRows 여유 확인용):")
    for r in routes:
        values = [counts[s][r] for s in counts if r in counts[s]]
        print(f"  {r}: max={max(values)} (수집 {len(values)}회)")


if __name__ == "__main__":
    main()

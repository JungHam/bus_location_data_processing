import json
import os
from datetime import datetime

from bus_api import get_bus_location_by_route

CITY_CODE = 21
ROUTE_ID = "BSB5200002000"


def main() -> None:
    buses = get_bus_location_by_route(CITY_CODE, ROUTE_ID)

    os.makedirs("data", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_path = f"data/bus_location_{ROUTE_ID}_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(buses, f, ensure_ascii=False, indent=2)

    print(f"{len(buses)}대의 버스 위치를 {out_path}에 저장했습니다.")


if __name__ == "__main__":
    main()

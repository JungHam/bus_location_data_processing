from bus_api import save_bus_location
from logging_config import configure_logging

CITY_CODE = 21
ROUTE_ID = "BSB5200002000"


def main() -> None:
    out_path = save_bus_location(CITY_CODE, ROUTE_ID)
    print(f"버스 위치를 {out_path}에 저장했습니다.")


if __name__ == "__main__":
    configure_logging()
    main()

import logging
import time
from datetime import datetime, timedelta

from bus_api import COLLECT_INTERVAL_MINUTES, logical_slot, save_bus_location
from logging_config import configure_logging

CITY_CODE = 21
ROUTE_IDS = ["BSB5200002000"]

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


def seconds_until_next_slot(now: datetime) -> float:
    next_slot = logical_slot(now) + timedelta(minutes=COLLECT_INTERVAL_MINUTES)
    return (next_slot - now).total_seconds()


def main() -> None:
    while True:
        now = datetime.now()
        collect_once(logical_slot(now))
        time.sleep(seconds_until_next_slot(datetime.now()))


if __name__ == "__main__":
    configure_logging()
    main()

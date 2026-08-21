import json
import logging
import os
import time
from datetime import datetime
from typing import Callable

import requests

import config
from fetch_json import fetch_json

TAGO_BUS_ROUTE_BASE = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService"
TAGO_BUS_LC_BASE = "https://apis.data.go.kr/1613000/BusLcInfoInqireService"
BUS_LOCATION_RAW_DIR = "data/raw/bus_location"

MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {404, 500, 502}

logger = logging.getLogger(__name__)


def _extract_items(payload: dict) -> list[dict]:
    header = payload["response"]["header"]
    if header["resultCode"] != "00":
        logger.error(
            "TAGO API resultCode error: %s %s", header["resultCode"], header["resultMsg"]
        )
        raise RuntimeError(f"TAGO API error: {header['resultCode']} {header['resultMsg']}")

    items = payload["response"]["body"]["items"]
    if items == "":
        return []
    item = items["item"]
    return item if isinstance(item, list) else [item]


def get_route_no_list(city_code: int, page_no: int = 1, num_of_rows: int = 1000) -> list[dict]:
    params = {
        "serviceKey": config.BUS_ROUTE_INFO_INQIRE_SERVICE_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "_type": "json",
        "cityCode": city_code,
    }
    payload = fetch_json(f"{TAGO_BUS_ROUTE_BASE}/getRouteNoList", params=params)
    return _extract_items(payload)


def _fetch_with_retry(fetch_fn: Callable[[], list[dict]], log_context: str) -> list[dict]:
    for attempt in range(MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES
        try:
            items = fetch_fn()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code not in RETRYABLE_STATUS_CODES:
                logger.error(
                    "Non-retryable HTTP error for %s: %s %s",
                    log_context,
                    e.response.status_code,
                    e.response.text,
                )
                raise
            if is_last_attempt:
                logger.error(
                    "Retries exhausted for %s: %s %s",
                    log_context,
                    e.response.status_code,
                    e.response.text,
                )
                raise
            time.sleep(2**attempt)
            continue

        if items:
            return items
        if is_last_attempt:
            logger.error(
                "Retries exhausted for %s: empty response after %s attempts",
                log_context,
                MAX_RETRIES + 1,
            )
            return items
        time.sleep(2**attempt)


def get_bus_location_by_route(
    city_code: int, route_id: str, page_no: int = 1, num_of_rows: int = 20
) -> list[dict]:
    params = {
        "serviceKey": config.BUS_LC_INFO_INQIRE_SERVICE_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "_type": "json",
        "cityCode": city_code,
        "routeId": route_id,
    }
    url = f"{TAGO_BUS_LC_BASE}/getRouteAcctoBusLcList"

    return _fetch_with_retry(
        lambda: _extract_items(fetch_json(url, params=params)),
        log_context=f"cityCode={city_code} routeId={route_id}",
    )


def save_bus_location(city_code: int, route_id: str) -> str:
    buses = get_bus_location_by_route(city_code, route_id)

    now = datetime.now()
    partition_dir = os.path.join(
        BUS_LOCATION_RAW_DIR, f"dt={now:%Y-%m-%d}", f"hour={now:%H}"
    )
    os.makedirs(partition_dir, exist_ok=True)

    out_path = os.path.join(partition_dir, f"{route_id}_{now:%Y%m%d%H%M%S}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(buses, f, ensure_ascii=False, indent=2)

    return out_path

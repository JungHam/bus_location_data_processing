import json
import logging
import os
import time
from datetime import datetime
from typing import Callable

import requests

import config
from fetch_json import fetch_json
from secrets_mask import mask_service_key

TAGO_BUS_ROUTE_BASE = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService"
TAGO_BUS_LC_BASE = "https://apis.data.go.kr/1613000/BusLcInfoInqireService"
BUS_LOCATION_RAW_DIR = "data/raw/bus_location"
# 노선당 최대 약 22대가 관측됐다(밤 시간대). 낮 피크 여유를 두어 100으로 잡는다.
BUS_LOCATION_NUM_OF_ROWS = 100

COLLECT_INTERVAL_MINUTES = 10

MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {404, 500, 502}
# 99: 서버 동시 세션 슬롯 소진("가용한 세션이 존재하지 않습니다 (30/30)") — 측정 중 관찰된 일시적 오류
RETRYABLE_RESULT_CODES = {"99"}

logger = logging.getLogger(__name__)


class TagoApiError(RuntimeError):
    def __init__(self, result_code: str, result_msg: str) -> None:
        super().__init__(f"TAGO API error: {result_code} {result_msg}")
        # 실제 응답은 resultCode를 숫자로 줄 때가 있어 문자열로 맞춘다
        self.result_code = str(result_code)


def _extract_items(payload: dict) -> list[dict]:
    header = payload["response"]["header"]
    if header["resultCode"] != "00":
        logger.error(
            "TAGO API resultCode error: %s %s", header["resultCode"], header["resultMsg"]
        )
        raise TagoApiError(header["resultCode"], header["resultMsg"])

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


def _retry_reason(error: Exception) -> str | None:
    """재시도할 만한 일시적 오류면 로그에 남길 사유를, 아니면 None을 돌려준다."""
    if isinstance(error, requests.exceptions.HTTPError):
        if error.response.status_code in RETRYABLE_STATUS_CODES:
            return f"HTTP {error.response.status_code}"
    elif isinstance(error, TagoApiError):
        if error.result_code in RETRYABLE_RESULT_CODES:
            return f"resultCode {error.result_code}"
    elif isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return type(error).__name__
    return None


def _describe(error: Exception) -> str:
    if isinstance(error, requests.exceptions.HTTPError):
        return f"HTTP {error.response.status_code} {error.response.text}"
    return mask_service_key(f"{type(error).__name__}: {error}")


def _fetch_with_retry(fetch_fn: Callable[[], list[dict]], log_context: str) -> list[dict]:
    for attempt in range(MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES
        try:
            items = fetch_fn()
        except (requests.exceptions.RequestException, TagoApiError) as e:
            reason = _retry_reason(e)
            if reason is None:
                logger.error("Non-retryable HTTP error for %s: %s", log_context, _describe(e))
                raise
            if is_last_attempt:
                logger.error("Retries exhausted for %s: %s", log_context, _describe(e))
                raise
            logger.warning(
                "Retry %s/%s for %s: %s", attempt + 1, MAX_RETRIES, log_context, reason
            )
            time.sleep(2**attempt)
            continue

        if items:
            logger.info(
                "Fetched %s: %s items after %s attempt(s)",
                log_context,
                len(items),
                attempt + 1,
            )
            return items
        if is_last_attempt:
            logger.error(
                "Retries exhausted for %s: empty response after %s attempts",
                log_context,
                MAX_RETRIES + 1,
            )
            return items
        logger.warning(
            "Retry %s/%s for %s: empty response", attempt + 1, MAX_RETRIES, log_context
        )
        time.sleep(2**attempt)


def _warn_if_truncated(payload: dict, items: list[dict], log_context: str) -> None:
    """totalCount가 받은 개수보다 크면 일부 차량이 빠진 것이므로 경고를 남긴다."""
    total = payload["response"]["body"].get("totalCount")
    if total is not None and int(total) > len(items):
        logger.warning(
            "Truncated response for %s: totalCount=%s but received %s items",
            log_context,
            total,
            len(items),
        )


def get_bus_location_by_route(
    city_code: int,
    route_id: str,
    page_no: int = 1,
    num_of_rows: int = BUS_LOCATION_NUM_OF_ROWS,
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
    log_context = f"cityCode={city_code} routeId={route_id}"

    def fetch_page() -> list[dict]:
        payload = fetch_json(url, params=params)
        items = _extract_items(payload)
        _warn_if_truncated(payload, items, log_context)
        return items

    return _fetch_with_retry(fetch_page, log_context=log_context)


def logical_slot(moment: datetime) -> datetime:
    """실행 시각을 수집 구간의 시작 시각으로 내린다. 같은 구간의 재실행은 같은 키가 된다."""
    minute = moment.minute - moment.minute % COLLECT_INTERVAL_MINUTES
    return moment.replace(minute=minute, second=0, microsecond=0)


def save_bus_location(
    city_code: int, route_id: str, slot: datetime | None = None
) -> str | None:
    """노선의 버스 위치를 수집 구간(slot) 키로 저장한다. 비어 있으면 저장하지 않고 None을 돌려준다.

    slot을 주지 않으면 지금 시각이 속한 구간을 쓴다. 오케스트레이터가 붙으면 논리 시각을 여기로 넘긴다.
    """
    buses = get_bus_location_by_route(city_code, route_id)
    if not buses:
        logger.warning("Skip saving empty response for routeId=%s", route_id)
        return None

    slot = logical_slot(slot or datetime.now())
    partition_dir = os.path.join(
        BUS_LOCATION_RAW_DIR, f"dt={slot:%Y-%m-%d}", f"hour={slot:%H}"
    )
    os.makedirs(partition_dir, exist_ok=True)

    out_path = os.path.join(partition_dir, f"{route_id}_{slot:%Y%m%d%H%M}.json")
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(buses, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)

    return out_path

import json
import logging
import os
from datetime import date

import requests

import config
from fetch_json import fetch_json

KMA_ASOS_HOURLY_URL = "https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList"
WEATHER_RAW_DIR = "data/raw/weather_asos_hourly"
# 부산 관측지점. startDt/endDt와 응답 tm은 KST다(일사량이 07~18시에만 값이 있는 것으로 확인).
BUSAN_STATION_ID = 159
HOURS_PER_DAY = 24

logger = logging.getLogger(__name__)


class AsosApiError(RuntimeError):
    def __init__(self, result_code: str, result_msg: str) -> None:
        super().__init__(f"ASOS API error: {result_code} {result_msg}")
        self.result_code = str(result_code)


class AsosServiceKeyError(AsosApiError):
    """공공데이터포털 게이트웨이가 서비스키를 거절했다(403, returnReasonCode 30). 재시도해도 풀리지 않는다.

    ASOS 서비스의 resultCode(예: 99 = 전날 자료까지 제공)와는 응답 모양과 코드 체계가 다르다.
    """


# 게이트웨이가 키를 거절할 때의 응답 코드. 403 본문의 OpenAPI_ServiceResponse.cmmMsgHeader에 들어 있다.
SERVICE_KEY_NOT_REGISTERED = "30"


def _raise_if_service_key_error(response: requests.Response) -> None:
    try:
        header = response.json()["OpenAPI_ServiceResponse"]["cmmMsgHeader"]
    except (ValueError, KeyError, TypeError):
        return
    if str(header.get("returnReasonCode")) == SERVICE_KEY_NOT_REGISTERED:
        logger.error("ASOS service key rejected: %s", header.get("errMsg"))
        # 키 오류에는 HTTPError의 정보(상태·URL)가 더 필요 없어 연결하지 않는다. 키 가리기는 fetch_json이 한다
        raise AsosServiceKeyError(
            SERVICE_KEY_NOT_REGISTERED, header.get("errMsg", "")
        ) from None


class AsosEmptyPayloadError(RuntimeError):
    """body가 없거나 하루치가 통째로 비었다. 게시 전일 수 있어 task 재시도에 맡긴다."""


def _extract_items(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or "response" not in payload:
        raise AsosEmptyPayloadError(f"Missing 'response' in payload: {str(payload)[:100]}")
    header = payload["response"]["header"]
    if header["resultCode"] != "00":
        logger.error(
            "ASOS resultCode error: %s %s", header["resultCode"], header["resultMsg"]
        )
        raise AsosApiError(header["resultCode"], header["resultMsg"])

    body = payload["response"].get("body")
    items = body.get("items") if body else None
    if not items:
        raise AsosEmptyPayloadError("No items in body")
    item = items["item"]
    return item if isinstance(item, list) else [item]


def get_hourly_by_date(day: date, station_id: int = BUSAN_STATION_ID) -> list[dict]:
    """KST 하루(00~23시)의 시간자료를 가져온다. 시간대 일부가 비는 것은 정상으로 보고 개수만 경고한다."""
    ymd = f"{day:%Y%m%d}"
    params = {
        "serviceKey": config.KMA_ASOS_HOURLY_SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 31,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "HR",
        "startDt": ymd,
        "startHh": "00",
        "endDt": ymd,
        "endHh": "23",
        "stnIds": station_id,
    }
    try:
        payload = fetch_json(KMA_ASOS_HOURLY_URL, params=params)
    except requests.exceptions.HTTPError as error:
        _raise_if_service_key_error(error.response)
        raise
    items = _extract_items(payload)
    if len(items) < HOURS_PER_DAY:
        logger.warning(
            "Missing hours for stnId=%s date=%s: %s of %s hours",
            station_id,
            day,
            len(items),
            HOURS_PER_DAY,
        )
    return items


def save_weather_day(day: date, station_id: int = BUSAN_STATION_ID) -> str:
    """논리 일 하나를 날짜 키 파일로 저장한다. 같은 날의 재실행은 같은 파일을 덮어쓴다."""
    items = get_hourly_by_date(day, station_id)

    partition_dir = os.path.join(WEATHER_RAW_DIR, f"dt={day:%Y-%m-%d}")
    os.makedirs(partition_dir, exist_ok=True)

    out_path = os.path.join(partition_dir, f"stn{station_id}_{day:%Y%m%d}.json")
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)

    return out_path

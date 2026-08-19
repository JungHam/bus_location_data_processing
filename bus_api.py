import config
from fetch_json import fetch_json

TAGO_BUS_ROUTE_BASE = "https://apis.data.go.kr/1613000/BusRouteInfoInqireService"
TAGO_BUS_LC_BASE = "https://apis.data.go.kr/1613000/BusLcInfoInqireService"


def _extract_items(payload: dict) -> list[dict]:
    header = payload["response"]["header"]
    if header["resultCode"] != "00":
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
    payload = fetch_json(f"{TAGO_BUS_LC_BASE}/getRouteAcctoBusLcList", params=params)
    return _extract_items(payload)

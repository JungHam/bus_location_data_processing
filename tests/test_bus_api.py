import json
import logging
import re
from unittest.mock import Mock

import pytest
import requests

import bus_api


def make_http_error(status_code: int, text: str = "") -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode("utf-8")
    return requests.exceptions.HTTPError(response=response)


def make_payload(item, result_code: str = "00", result_msg: str = "NORMAL SERVICE.") -> dict:
    return {
        "response": {
            "header": {"resultCode": result_code, "resultMsg": result_msg},
            "body": {"items": "" if item is None else {"item": item}},
        }
    }


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(bus_api.time, "sleep", lambda seconds: None)


class TestExtractItems:
    def test_single_item_is_wrapped_in_a_list(self):
        payload = make_payload({"routeId": "A"})
        assert bus_api._extract_items(payload) == [{"routeId": "A"}]

    def test_multiple_items_are_returned_as_is(self):
        payload = make_payload([{"routeId": "A"}, {"routeId": "B"}])
        assert bus_api._extract_items(payload) == [{"routeId": "A"}, {"routeId": "B"}]

    def test_no_items_returns_empty_list(self):
        payload = make_payload(None)
        assert bus_api._extract_items(payload) == []

    def test_result_code_error_raises_and_logs(self, caplog):
        payload = make_payload(None, result_code="99", result_msg="UNKNOWN ERROR")
        with caplog.at_level(logging.ERROR, logger="bus_api"):
            with pytest.raises(RuntimeError, match="99"):
                bus_api._extract_items(payload)
        assert "resultCode error" in caplog.text
        assert "99" in caplog.text


class TestFetchWithRetry:
    def test_retryable_http_error_then_success(self):
        fetch_fn = Mock(side_effect=[make_http_error(502), make_http_error(502), ["ok"]])
        result = bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert result == ["ok"]
        assert fetch_fn.call_count == 3

    def test_empty_result_then_success(self):
        fetch_fn = Mock(side_effect=[[], [], ["ok"]])
        result = bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert result == ["ok"]
        assert fetch_fn.call_count == 3

    def test_retryable_http_error_exhausts_retries(self, caplog):
        fetch_fn = Mock(side_effect=make_http_error(404))
        with caplog.at_level(logging.ERROR, logger="bus_api"):
            with pytest.raises(requests.exceptions.HTTPError):
                bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert fetch_fn.call_count == bus_api.MAX_RETRIES + 1
        assert "Retries exhausted" in caplog.text

    def test_non_retryable_http_error_raises_immediately(self, caplog):
        fetch_fn = Mock(side_effect=make_http_error(401, "unauthorized"))
        with caplog.at_level(logging.ERROR, logger="bus_api"):
            with pytest.raises(requests.exceptions.HTTPError):
                bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert fetch_fn.call_count == 1
        assert "Non-retryable HTTP error" in caplog.text

    def test_empty_result_exhausts_retries_and_returns_empty_list(self, caplog):
        fetch_fn = Mock(return_value=[])
        with caplog.at_level(logging.ERROR, logger="bus_api"):
            result = bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert result == []
        assert fetch_fn.call_count == bus_api.MAX_RETRIES + 1
        assert "Retries exhausted" in caplog.text


class TestGetRouteNoList:
    def test_builds_request_and_returns_extracted_items(self, monkeypatch):
        mock_fetch_json = Mock(return_value=make_payload([{"routeId": "A"}]))
        monkeypatch.setattr(bus_api, "fetch_json", mock_fetch_json)

        result = bus_api.get_route_no_list(city_code=21, num_of_rows=5)

        assert result == [{"routeId": "A"}]
        url, kwargs = mock_fetch_json.call_args
        assert url[0] == f"{bus_api.TAGO_BUS_ROUTE_BASE}/getRouteNoList"
        assert kwargs["params"]["cityCode"] == 21
        assert kwargs["params"]["numOfRows"] == 5
        assert kwargs["params"]["serviceKey"] == bus_api.config.BUS_ROUTE_INFO_INQIRE_SERVICE_KEY


class TestGetBusLocationByRoute:
    def test_builds_request_and_returns_extracted_items(self, monkeypatch):
        mock_fetch_json = Mock(return_value=make_payload([{"vehicleno": "70자1234"}]))
        monkeypatch.setattr(bus_api, "fetch_json", mock_fetch_json)

        result = bus_api.get_bus_location_by_route(city_code=21, route_id="BSB5200002000")

        assert result == [{"vehicleno": "70자1234"}]
        url, kwargs = mock_fetch_json.call_args
        assert url[0] == f"{bus_api.TAGO_BUS_LC_BASE}/getRouteAcctoBusLcList"
        assert kwargs["params"]["cityCode"] == 21
        assert kwargs["params"]["routeId"] == "BSB5200002000"
        assert kwargs["params"]["serviceKey"] == bus_api.config.BUS_LC_INFO_INQIRE_SERVICE_KEY


class TestSaveBusLocation:
    def test_saves_json_under_hive_style_partition(self, monkeypatch, tmp_path):
        raw_dir = tmp_path / "bus_location"
        monkeypatch.setattr(bus_api, "BUS_LOCATION_RAW_DIR", str(raw_dir))
        buses = [{"vehicleno": "70자1234"}]
        monkeypatch.setattr(bus_api, "get_bus_location_by_route", Mock(return_value=buses))

        out_path = bus_api.save_bus_location(city_code=21, route_id="BSB5200002000")

        assert re.search(r"dt=\d{4}-\d{2}-\d{2}/hour=\d{2}/", out_path)
        with open(out_path, encoding="utf-8") as f:
            assert json.load(f) == buses

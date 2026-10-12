import json
import logging
import re
from datetime import datetime
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
        payload = make_payload(None, result_code=99, result_msg="UNKNOWN ERROR")
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


class TestLogicalSlot:
    @pytest.mark.parametrize(
        "moment, expected",
        [
            (datetime(2026, 10, 12, 10, 19, 59), datetime(2026, 10, 12, 10, 10)),
            (datetime(2026, 10, 12, 10, 10, 0), datetime(2026, 10, 12, 10, 10)),  # 경계 정각
            (datetime(2026, 10, 12, 10, 9, 59, 999999), datetime(2026, 10, 12, 10, 0)),  # 경계 직전
            (datetime(2026, 10, 12, 10, 0, 0), datetime(2026, 10, 12, 10, 0)),  # 정시
            (datetime(2026, 10, 12, 10, 59, 59), datetime(2026, 10, 12, 10, 50)),  # 시간 끝
            (datetime(2026, 10, 12, 0, 0, 0), datetime(2026, 10, 12, 0, 0)),  # 자정
            (datetime(2026, 10, 12, 23, 59, 59, 999999), datetime(2026, 10, 12, 23, 50)),  # 날짜 안 넘어감
            (datetime(2026, 10, 12, 10, 10, 0, 500000), datetime(2026, 10, 12, 10, 10)),  # 마이크로초 제거
        ],
    )
    def test_floors_to_collect_interval(self, moment, expected):
        assert bus_api.logical_slot(moment) == expected

    def test_every_minute_maps_to_its_ten_minute_slot(self):
        for minute in range(60):
            slot = bus_api.logical_slot(datetime(2026, 10, 12, 10, minute, 30))
            assert slot == datetime(2026, 10, 12, 10, minute // 10 * 10)

    def test_is_idempotent(self):
        once = bus_api.logical_slot(datetime(2026, 10, 12, 10, 47, 12))
        assert bus_api.logical_slot(once) == once


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

    def test_rerun_in_same_slot_overwrites_same_key(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bus_api, "BUS_LOCATION_RAW_DIR", str(tmp_path / "bus_location"))
        monkeypatch.setattr(
            bus_api, "get_bus_location_by_route", Mock(return_value=[{"vehicleno": "a"}])
        )

        paths = {
            bus_api.save_bus_location(21, "BSB1", datetime(2026, 10, 12, 10, minute))
            for minute in (1, 5, 9)
        }

        assert len(paths) == 1
        assert len(list((tmp_path / "bus_location").rglob("*.json"))) == 1

    def test_different_slots_make_different_keys(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bus_api, "BUS_LOCATION_RAW_DIR", str(tmp_path / "bus_location"))
        monkeypatch.setattr(
            bus_api, "get_bus_location_by_route", Mock(return_value=[{"vehicleno": "a"}])
        )

        first = bus_api.save_bus_location(21, "BSB1", datetime(2026, 10, 12, 10, 9))
        second = bus_api.save_bus_location(21, "BSB1", datetime(2026, 10, 12, 10, 10))

        assert first != second

    def test_empty_response_is_not_saved(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setattr(bus_api, "BUS_LOCATION_RAW_DIR", str(tmp_path / "bus_location"))
        monkeypatch.setattr(bus_api, "get_bus_location_by_route", Mock(return_value=[]))

        assert bus_api.save_bus_location(21, "BSB1") is None
        assert not (tmp_path / "bus_location").exists()

    def test_empty_response_does_not_overwrite_existing_data(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bus_api, "BUS_LOCATION_RAW_DIR", str(tmp_path / "bus_location"))
        slot = datetime(2026, 10, 12, 10, 3)
        good = [{"vehicleno": "a"}]
        monkeypatch.setattr(bus_api, "get_bus_location_by_route", Mock(return_value=good))
        out_path = bus_api.save_bus_location(21, "BSB1", slot)
        monkeypatch.setattr(bus_api, "get_bus_location_by_route", Mock(return_value=[]))

        bus_api.save_bus_location(21, "BSB1", slot)

        with open(out_path, encoding="utf-8") as f:
            assert json.load(f) == good


class TestRetryLogging:
    def test_retry_attempts_are_logged_with_reason(self, caplog):
        fetch_fn = Mock(side_effect=[make_http_error(404), [], ["ok"]])
        with caplog.at_level(logging.WARNING, logger="bus_api"):
            bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        messages = [r.getMessage() for r in caplog.records]
        assert messages == [
            "Retry 1/3 for ctx: HTTP 404",
            "Retry 2/3 for ctx: empty response",
        ]

    def test_success_logs_attempt_count(self, caplog):
        fetch_fn = Mock(side_effect=[[], ["ok"]])
        with caplog.at_level(logging.INFO, logger="bus_api"):
            bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert "after 2 attempt(s)" in caplog.text


class TestFetchJsonTimeout:
    def test_default_timeout_is_applied(self, monkeypatch):
        import fetch_json

        get = Mock(return_value=Mock(content=b"{}", raise_for_status=lambda: None))
        monkeypatch.setattr(fetch_json.requests, "get", get)
        fetch_json.fetch_json("http://x")
        assert get.call_args.kwargs["timeout"] == fetch_json.DEFAULT_TIMEOUT


class TestTransientErrorRetry:
    def test_session_exhausted_result_code_is_retried(self):
        busy = bus_api.TagoApiError(99, "가용한 세션이 존재하지 않습니다. (30/30)")
        fetch_fn = Mock(side_effect=[busy, ["ok"]])
        assert bus_api._fetch_with_retry(fetch_fn, log_context="ctx") == ["ok"]
        assert fetch_fn.call_count == 2

    def test_numeric_result_code_99_in_real_payload_shape_is_retried(self, monkeypatch):
        busy = make_payload(None, result_code=99, result_msg="가용한 세션이 존재하지 않습니다. (30/30)")
        mock_fetch_json = Mock(side_effect=[busy, make_payload([{"vehicleno": "a"}])])
        monkeypatch.setattr(bus_api, "fetch_json", mock_fetch_json)

        result = bus_api.get_bus_location_by_route(city_code=21, route_id="BSB1")

        assert result == [{"vehicleno": "a"}]
        assert mock_fetch_json.call_count == 2

    def test_other_result_code_is_not_retried(self):
        fetch_fn = Mock(side_effect=bus_api.TagoApiError("30", "SERVICE KEY IS NOT REGISTERED"))
        with pytest.raises(bus_api.TagoApiError):
            bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert fetch_fn.call_count == 1

    @pytest.mark.parametrize(
        "error", [requests.exceptions.ConnectionError(), requests.exceptions.Timeout()]
    )
    def test_connection_errors_are_retried(self, error):
        fetch_fn = Mock(side_effect=[error, ["ok"]])
        assert bus_api._fetch_with_retry(fetch_fn, log_context="ctx") == ["ok"]
        assert fetch_fn.call_count == 2

    def test_connection_error_exhausts_retries(self):
        fetch_fn = Mock(side_effect=requests.exceptions.ConnectionError())
        with pytest.raises(requests.exceptions.ConnectionError):
            bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert fetch_fn.call_count == bus_api.MAX_RETRIES + 1


class TestServiceKeyMasking:
    URL_ERROR = (
        "HTTPSConnectionPool(host='apis.data.go.kr'): Max retries exceeded with url: "
        "/getRouteAcctoBusLcList?serviceKey=SECRET%2Bkey%3D%3D&pageNo=1&cityCode=21"
    )

    def test_mask_service_key_hides_value_only(self):
        from secrets_mask import mask_service_key

        masked = mask_service_key(self.URL_ERROR)
        assert "SECRET" not in masked
        assert "serviceKey=***&pageNo=1" in masked

    def test_connection_error_is_masked_in_retry_logs(self, caplog):
        fetch_fn = Mock(side_effect=requests.exceptions.ConnectionError(self.URL_ERROR))
        with caplog.at_level(logging.ERROR, logger="bus_api"):
            with pytest.raises(requests.exceptions.ConnectionError):
                bus_api._fetch_with_retry(fetch_fn, log_context="ctx")
        assert "SECRET" not in caplog.text
        assert "serviceKey=***" in caplog.text

    def test_logging_filter_masks_any_record(self):
        from secrets_mask import MaskServiceKeyFilter

        record = logging.LogRecord("x", logging.ERROR, "f", 1, "failed: %s", (self.URL_ERROR,), None)
        MaskServiceKeyFilter().filter(record)
        assert "SECRET" not in record.getMessage()

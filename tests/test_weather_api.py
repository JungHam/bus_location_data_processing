import json
import logging
import os
from datetime import date

import pytest

import weather_api


def make_item(hour: int, day: str = "2026-10-21") -> dict:
    return {"tm": f"{day} {hour:02d}:00", "stnId": "159", "ta": "17.9"}


def make_payload(items, result_code: str = "00", result_msg: str = "NORMAL_SERVICE") -> dict:
    response = {"header": {"resultCode": result_code, "resultMsg": result_msg}}
    if items is not None:
        response["body"] = {"items": {"item": items}, "totalCount": len(items)}
    return {"response": response}


def full_day() -> list[dict]:
    return [make_item(hour) for hour in range(24)]


class TestExtractItems:
    def test_multiple_items_are_returned_as_is(self):
        items = [make_item(0), make_item(1)]
        assert weather_api._extract_items(make_payload(items)) == items

    def test_single_item_is_wrapped_in_a_list(self):
        item = make_item(0)
        assert weather_api._extract_items(make_payload(item)) == [item]

    def test_result_code_error_raises_with_code_and_logs(self, caplog):
        payload = make_payload(None, result_code="99", result_msg="전날 자료까지 제공됩니다.")
        with caplog.at_level(logging.ERROR, logger="weather_api"):
            with pytest.raises(weather_api.AsosApiError) as exc_info:
                weather_api._extract_items(payload)
        assert exc_info.value.result_code == "99"
        assert "resultCode error" in caplog.text

    def test_missing_body_raises_empty_payload_error(self):
        with pytest.raises(weather_api.AsosEmptyPayloadError):
            weather_api._extract_items(make_payload(None))


class TestGetHourlyByDate:
    def test_requests_one_kst_day_for_the_station(self, monkeypatch):
        captured = {}

        def fake_fetch_json(url, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs["params"]
            return make_payload(full_day())

        monkeypatch.setattr(weather_api, "fetch_json", fake_fetch_json)

        weather_api.get_hourly_by_date(date(2026, 10, 21))

        params = captured["params"]
        assert captured["url"] == weather_api.KMA_ASOS_HOURLY_URL
        assert params["startDt"] == params["endDt"] == "20261021"
        assert (params["startHh"], params["endHh"]) == ("00", "23")
        assert params["stnIds"] == weather_api.BUSAN_STATION_ID
        assert params["dataCd"] == "ASOS" and params["dateCd"] == "HR"

    def test_full_day_returns_items_without_warning(self, monkeypatch, caplog):
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: make_payload(full_day()))

        with caplog.at_level(logging.WARNING, logger="weather_api"):
            items = weather_api.get_hourly_by_date(date(2026, 10, 21))

        assert len(items) == 24
        assert "Missing hours" not in caplog.text

    def test_missing_hours_are_returned_with_a_warning(self, monkeypatch, caplog):
        partial = [make_item(hour) for hour in range(20)]
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: make_payload(partial))

        with caplog.at_level(logging.WARNING, logger="weather_api"):
            items = weather_api.get_hourly_by_date(date(2026, 10, 21))

        assert items == partial
        assert "20 of 24 hours" in caplog.text


class TestSaveWeatherDay:
    @pytest.fixture(autouse=True)
    def raw_dir(self, monkeypatch, tmp_path):
        directory = str(tmp_path / "weather")
        monkeypatch.setattr(weather_api, "WEATHER_RAW_DIR", directory)
        return directory

    def test_saves_under_a_date_key(self, monkeypatch, raw_dir):
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: make_payload(full_day()))

        out_path = weather_api.save_weather_day(date(2026, 10, 21))

        assert out_path == os.path.join(raw_dir, "dt=2026-10-21", "stn159_20261021.json")
        with open(out_path, encoding="utf-8") as f:
            assert json.load(f) == full_day()

    def test_rerun_of_the_same_day_overwrites_the_same_file(self, monkeypatch):
        first = [make_item(0)]
        second = full_day()
        responses = iter([make_payload(first), make_payload(second)])
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: next(responses))

        first_path = weather_api.save_weather_day(date(2026, 10, 21))
        second_path = weather_api.save_weather_day(date(2026, 10, 21))

        assert first_path == second_path
        with open(second_path, encoding="utf-8") as f:
            assert len(json.load(f)) == 24

    def test_each_day_saves_its_own_24_hours(self, monkeypatch):
        def fake_fetch_json(url, **kwargs):
            ymd = kwargs["params"]["startDt"]
            day = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
            return make_payload([make_item(hour, day) for hour in range(24)])

        monkeypatch.setattr(weather_api, "fetch_json", fake_fetch_json)

        for day, label in [(date(2026, 10, 20), "2026-10-20"), (date(2026, 10, 21), "2026-10-21")]:
            with open(weather_api.save_weather_day(day), encoding="utf-8") as f:
                saved = json.load(f)
            assert len(saved) == 24
            assert {item["tm"][:10] for item in saved} == {label}

    def test_failure_while_writing_keeps_the_previous_file_intact(self, monkeypatch):
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: make_payload(full_day()))
        out_path = weather_api.save_weather_day(date(2026, 10, 21))
        with open(out_path, encoding="utf-8") as f:
            before = f.read()

        def broken_dump(obj, fp, **kwargs):
            fp.write('{"partial": ')
            raise OSError("disk full")

        monkeypatch.setattr(weather_api.json, "dump", broken_dump)

        with pytest.raises(OSError, match="disk full"):
            weather_api.save_weather_day(date(2026, 10, 21))

        with open(out_path, encoding="utf-8") as f:
            assert f.read() == before

    def test_empty_payload_raises_and_writes_nothing(self, monkeypatch, raw_dir):
        monkeypatch.setattr(weather_api, "fetch_json", lambda url, **kw: make_payload(None))

        with pytest.raises(weather_api.AsosEmptyPayloadError):
            weather_api.save_weather_day(date(2026, 10, 21))

        assert not os.path.exists(raw_dir)

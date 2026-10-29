import pytest
import requests

import fetch_json

URL_WITH_KEY = "https://apis.example.com/api?serviceKey=REAL_KEY&pageNo=1"


def response_with_status(status: int) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = URL_WITH_KEY
    response.request = requests.Request("GET", URL_WITH_KEY).prepare()
    response._content = b'{"message": "error"}'
    return response


class TestServiceKeyIsNotInRaisedErrors:
    def test_http_error_keeps_type_and_response_but_not_the_key(self, monkeypatch):
        monkeypatch.setattr(fetch_json.requests, "get", lambda url, **kwargs: response_with_status(500))

        with pytest.raises(requests.exceptions.HTTPError) as exc_info:
            fetch_json.fetch_json("https://apis.example.com/api", params={"serviceKey": "REAL_KEY"})

        error = exc_info.value
        assert "REAL_KEY" not in str(error)
        assert "REAL_KEY" not in error.response.url
        assert "REAL_KEY" not in error.request.url
        assert error.response.status_code == 500
        assert error.__context__ is None and error.__cause__ is None

    def test_connection_error_keeps_its_type_for_retry_decisions(self, monkeypatch):
        def fail(url, **kwargs):
            raise requests.exceptions.ConnectTimeout(f"Max retries exceeded with url: {URL_WITH_KEY}")

        monkeypatch.setattr(fetch_json.requests, "get", fail)

        with pytest.raises(requests.exceptions.ConnectTimeout) as exc_info:
            fetch_json.fetch_json("https://apis.example.com/api")

        error = exc_info.value
        assert isinstance(error, requests.exceptions.ConnectionError)
        assert isinstance(error, requests.exceptions.Timeout)
        assert "REAL_KEY" not in str(error)
        assert error.__context__ is None

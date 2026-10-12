import json

import requests

# (연결, 읽기) 초. 측정에서 응답 시간 p95가 약 5초여서 읽기는 여유를 둔다.
DEFAULT_TIMEOUT = (5, 10)


def fetch_json(url: str, **kwargs) -> dict | list:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return json.loads(response.content.decode("utf-8"))


if __name__ == "__main__":
    url = "https://example.com/api"
    data = fetch_json(url)
    print(data)

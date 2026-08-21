import json

import requests


def fetch_json(url: str, **kwargs) -> dict | list:
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return json.loads(response.content.decode("utf-8"))


if __name__ == "__main__":
    url = "https://example.com/api"
    data = fetch_json(url)
    print(data)

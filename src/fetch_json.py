import json

import requests

from secrets_mask import mask_service_key

# (연결, 읽기) 초. 측정에서 응답 시간 p95가 약 5초여서 읽기는 여유를 둔다.
DEFAULT_TIMEOUT = (5, 10)


def _without_service_key(error: requests.exceptions.RequestException) -> requests.exceptions.RequestException:
    """같은 타입·같은 response로 메시지의 serviceKey만 가린 예외를 만든다.

    호출하는 쪽은 예외 타입(HTTPError/ConnectionError/Timeout)과 error.response로 재시도·키 오류를 판단한다.
    """
    if error.response is not None and error.response.url:
        error.response.url = mask_service_key(error.response.url)
    if error.request is not None and error.request.url:
        error.request.url = mask_service_key(error.request.url)
    
    return type(error)(
        mask_service_key(str(error)), response=error.response, request=error.request
    )


def fetch_json(url: str, **kwargs) -> dict | list:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    masked_error = None
    try:
        response = requests.get(url, **kwargs)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        masked_error = _without_service_key(error)
    if masked_error is not None:        
        # except 블록 밖에서 던져 원래 예외(메시지에 키가 든 URL)가 __context__로 남지 않게 한다
        raise masked_error
    return json.loads(response.content.decode("utf-8"))


if __name__ == "__main__":
    url = "https://example.com/api"
    data = fetch_json(url)
    print(data)

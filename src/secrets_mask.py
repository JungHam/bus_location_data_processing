import logging
import re

# 요청 URL이 예외 메시지에 그대로 들어오는 경우(requests ConnectionError 등)를 가린다.
_SERVICE_KEY = re.compile(r"(serviceKey=)[^&\s'\")]+", re.IGNORECASE)


def mask_service_key(text: str) -> str:
    return _SERVICE_KEY.sub(r"\1***", text)


class MaskServiceKeyFilter(logging.Filter):
    """어떤 경로로 로그가 만들어지든 마지막에 serviceKey 값을 가리는 안전망."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_service_key(record.getMessage())
        record.args = ()
        return True

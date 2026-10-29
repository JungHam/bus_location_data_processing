import csv
import hashlib
import os
import shutil

# 2023-07-31 기준 1회성 파일(갱신 없음). 기준일이 파일 이름에 있으므로 이름을 그대로 raw 키로 쓴다.
BOARDING_SOURCE_PATH = "data/external/busan_boarding/busan_bus_boarding_20230731.csv"
BOARDING_RAW_DIR = "data/raw/busan_boarding"
BOARDING_ENCODING = "cp949"


class BoardingRawMismatchError(RuntimeError):
    """raw 사본이 원본과 다를 때 낸다."""


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_boarding_raw(source_path: str = BOARDING_SOURCE_PATH) -> str:
    """원본을 바이트 그대로 raw에 복사한다. 같은 파일의 재실행은 같은 파일을 덮어쓴다."""
    os.makedirs(BOARDING_RAW_DIR, exist_ok=True)

    out_path = os.path.join(BOARDING_RAW_DIR, os.path.basename(source_path))
    tmp_path = f"{out_path}.tmp"
    shutil.copyfile(source_path, tmp_path)
    os.replace(tmp_path, out_path)

    return out_path


def check_boarding_raw(raw_path: str, source_path: str = BOARDING_SOURCE_PATH) -> dict:
    """raw 사본이 원본과 같은지 해시로 보고, 행 수·열 수를 센다."""
    raw_hash = sha256_of(raw_path)
    source_hash = sha256_of(source_path)
    if raw_hash != source_hash:
        raise BoardingRawMismatchError(f"{raw_path} differs from {source_path}")

    with open(raw_path, encoding=BOARDING_ENCODING, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        row_count = sum(1 for _ in reader)

    return {"path": raw_path, "sha256": raw_hash, "rows": row_count, "columns": len(header)}

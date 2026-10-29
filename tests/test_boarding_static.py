import os

import pytest

import boarding_static


@pytest.fixture
def source_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(boarding_static, "BOARDING_RAW_DIR", str(tmp_path / "raw"))
    path = tmp_path / "busan_bus_boarding_20230731.csv"
    # 행 수(2)와 열 수(3)를 다르게 둬서 둘이 뒤바뀌어도 테스트가 잡게 한다
    path.write_bytes("노선번호,정류장순서,정류장명\n10,0,차고지\n10,1,조합\n".encode("cp949"))
    return str(path)


class TestSaveBoardingRaw:
    def test_rerun_overwrites_the_same_file(self, source_csv):
        first = boarding_static.save_boarding_raw(source_csv)
        second = boarding_static.save_boarding_raw(source_csv)

        assert first == second
        assert os.listdir(boarding_static.BOARDING_RAW_DIR) == ["busan_bus_boarding_20230731.csv"]

    def test_copy_keeps_source_bytes(self, source_csv):
        out_path = boarding_static.save_boarding_raw(source_csv)

        assert boarding_static.sha256_of(out_path) == boarding_static.sha256_of(source_csv)


class TestCheckBoardingRaw:
    def test_counts_rows_and_columns(self, source_csv):
        out_path = boarding_static.save_boarding_raw(source_csv)

        summary = boarding_static.check_boarding_raw(out_path, source_csv)

        assert summary["rows"] == 2
        assert summary["columns"] == 3

    def test_modified_copy_raises(self, source_csv):
        out_path = boarding_static.save_boarding_raw(source_csv)
        with open(out_path, "ab") as f:
            f.write(b"10,2,x\n")

        with pytest.raises(boarding_static.BoardingRawMismatchError):
            boarding_static.check_boarding_raw(out_path, source_csv)

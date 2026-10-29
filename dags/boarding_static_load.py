import pendulum
from airflow.sdk import dag, task

KST = "Asia/Seoul"


@dag(
    dag_id="boarding_static_load",
    # 승하차 통계는 1회성 파일이라 주기 실행이 없다. 필요할 때 수동으로 trigger한다.
    schedule=None,
    start_date=pendulum.datetime(2026, 10, 28, tz=KST),
    catchup=False,
    max_active_runs=1,
)
def boarding_static_load():
    @task
    def load(dag_run) -> str:
        from boarding_static import save_boarding_raw

        # 저장 키는 파일 이름뿐이라 logical_date를 쓰지 않는다. 수동 run에서 무엇이 찍히는지만 본다.
        print(f"load: run_id={dag_run.run_id} logical_date={dag_run.logical_date}")

        out_path = save_boarding_raw()
        print(f"Saved {out_path}")
        # 데이터가 아니라 경로만 반환한다 → XCom에는 이 문자열만 남는다
        return out_path

    @task
    def check(raw_path: str) -> dict:
        from airflow.sdk.exceptions import AirflowFailException

        from boarding_static import BoardingRawMismatchError, check_boarding_raw

        try:
            summary = check_boarding_raw(raw_path)
        except BoardingRawMismatchError as error:
            # 복사가 원본과 다르면 다시 돌려도 같은 결과일 가능성이 커서 바로 실패시킨다
            raise AirflowFailException(str(error)) from error
        print(f"check: {summary}")
        return summary

    check(load())


boarding_static_load()

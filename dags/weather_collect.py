from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

KST = "Asia/Seoul"


@dag(
    dag_id="weather_collect",
    # 전일 자료는 당일 10시 이후 확인 가능하다는 설명이 있어 정오(KST)에 돈다
    schedule="0 12 * * *",
    start_date=pendulum.datetime(2026, 10, 18, tz=KST),
    catchup=True,
    max_active_runs=2,
)
def weather_collect():
    @task(
        retries=3,
        retry_delay=timedelta(seconds=30),
        retry_exponential_backoff=2.0,
    )
    def collect(ti, dag_run):
        from airflow.sdk.exceptions import AirflowFailException

        from weather_api import save_weather_day

        logical = dag_run.logical_date
        print(
            f"{ti.task_id}: logical_date={logical} "
            f"data_interval={dag_run.data_interval_start} ~ {dag_run.data_interval_end}"
        )

        # 12시 run이 어제(KST) 하루를 조회한다. 오늘 이후는 API가 99를 주므로 재시도 없이 실패시킨다.
        day = pendulum.instance(logical).in_timezone(KST).subtract(days=1).date()
        if day >= pendulum.now(KST).date():
            raise AirflowFailException(f"{day} is not available yet (API serves up to D-1)")

        print(f"{ti.task_id}: collecting {day}")
        out_path = save_weather_day(day)
        print(f"Saved {out_path}")

    collect()


weather_collect()

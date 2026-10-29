from datetime import datetime, timedelta, timezone

import pendulum
from alerting import send_failure_email
from airflow.sdk import dag, task

@dag(
    dag_id="bus_location_collect",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
    catchup=False,
)
def bus_location_collect() :
    @task(
            retries=1, 
            retry_delay=timedelta(seconds=10),
            on_failure_callback=send_failure_email,
            )
    def collect(ti, dag_run) :
        from collect_data import collect_once

        # 저장 키(dt=/hour=/파일 이름)는 KST로 만든다. 기존 nohup 수집 파일·기상 데이터와 같은 기준이다.
        # logical_date(UTC)를 그대로 넘기면 같은 이름이 다른 시각을 가리켜 파일을 덮어쓴다(2026-10-26).
        slot = pendulum.instance(dag_run.logical_date).in_timezone("Asia/Seoul")
        print(f"{ti.task_id} save data for slot {slot}, with task start at {ti.start_date}, try {ti.try_number}")
        # 재시도(try_number > 1)에서는 앞 시도에 저장된 노선을 건너뛰어 실패한 노선만 다시 받는다
        collect_once(slot, raise_on_failure=True, skip_existing=ti.try_number > 1)
    collect()

bus_location_collect()


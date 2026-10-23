from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task

@dag(
    dag_id="bus_location_collect",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
    catchup=False,
)
def bus_location_collect() :
    @task(retries=1, retry_delay=timedelta(seconds=10))
    def collect(ti, dag_run) :
        from collect_data import collect_once

        slot = dag_run.logical_date
        print(f"{ti.task_id} save data for slot {slot}, with task start at {ti.start_date}, try {ti.try_number}")
        # 재시도(try_number > 1)에서는 앞 시도에 저장된 노선을 건너뛰어 실패한 노선만 다시 받는다
        collect_once(slot, raise_on_failure=True, skip_existing=ti.try_number > 1)
    collect()

bus_location_collect()


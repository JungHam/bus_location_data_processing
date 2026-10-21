from datetime import datetime, timezone

from airflow.sdk import dag, task

@dag(
    dag_id="bus_location_collect",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
    catchup=False,
)
def bus_location_collect() : 
    @task
    def collect(ti, dag_run) : 
        from collect_data import collect_once

        slot = dag_run.logical_date
        print(f"{ti.task_id} save data for slot {slot}, with task start at {ti.start_date}")
        collect_once(slot)
    collect()

bus_location_collect()
    

from datetime import timedelta
from airflow.sdk import dag,task,get_current_context
from pendulum import datetime
import warehouse


@dag(schedule="0 3 * * *",start_date=datetime(2026,1,1,tz="UTC"),catchup=True,max_active_runs=2)
def daily_orders():
    @task(retries=2,retry_delay=timedelta(seconds=1),execution_timeout=timedelta(seconds=30))
    def build_partition():
        context=get_current_context()
        partition=(context['dag_run'].conf or {}).get('partition')
        if partition is None:
            start=context.get('data_interval_start')
            if start is None:
                raise ValueError('supply conf.partition for a run without an interval')
            partition=start.format('YYYY-MM-DD')
        warehouse.upsert_daily_orders(partition)
        return partition
    @task(retries=0)
    def check_partition(partition):
        if not warehouse.partition_is_valid(partition):
            raise ValueError('invalid partition')
    check_partition(build_partition())


dag_instance=daily_orders()

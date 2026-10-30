from airflow.sdk import dag, task
from pendulum import datetime


@dag(schedule="0 3 * * *",start_date=datetime(2026,1,1,tz="UTC"),catchup=False)
def daily_customer_counts():
    @task
    def count_customers(): return 42
    @task
    def record_metric(count): print(f"warehouse.customers = {count}")
    record_metric(count_customers())


dag_instance=daily_customer_counts()

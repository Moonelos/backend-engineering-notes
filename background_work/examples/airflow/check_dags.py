"""Run after airflow db migrate with the documented local environment."""
import os
import sqlite3
from pathlib import Path
from airflow.models import DagBag
from dags.daily_orders import dag_instance as orders
from dags.daily_customer_counts import dag_instance as counts

bag=DagBag(dag_folder=str(Path(__file__).parent/'dags'))
assert not bag.import_errors,bag.import_errors
assert set(orders.task_dict)=={'build_partition','check_partition'}
assert orders.get_task('check_partition').upstream_task_ids=={'build_partition'}
assert orders.max_active_runs==2
first=counts.test()
assert first.state=='success'
for _ in range(2):
    run=orders.test(run_conf={'partition':'2026-02-01'})
    assert run.state=='success'
with sqlite3.connect(os.environ['WAREHOUSE_DB']) as conn:
    assert conn.execute('SELECT day,orders FROM partitions').fetchall()==[('2026-02-01',42)]
print('DAGs parsed, counts=42, repeated partition still has one row')

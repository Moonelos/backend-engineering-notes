"""Disposable PostgreSQL -> Debezium -> Kafka outage/restart experiment.
Run from the repository root with Python 3.11+ and Docker; no host ports or volumes.
"""
import json
import subprocess
import time
import uuid

prefix = 'notes-cdc-' + uuid.uuid4().hex[:8]
network, pg, broker, connect = (prefix + x for x in ('-net', '-pg', '-kafka', '-connect'))
containers = []


def docker(*args, stdin=None, timeout=60):
    result = subprocess.run(['docker', *args], input=stdin, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'docker {args[0]} failed: {result.stderr[-2000:]}')
    return result.stdout.strip()


def wait_for(probe, description, seconds=120):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            last = error
        time.sleep(1)
    raise TimeoutError(f'{description}: {last}')


def sql(statement):
    return docker('exec', '-i', pg, 'psql', '-U', 'postgres', '-v', 'ON_ERROR_STOP=1',
                  '-At', stdin=statement)


def api(path, body=None, method=None):
    args = ['exec', '-i', connect, 'curl', '--fail', '--silent', '--show-error',
            '--max-time', '10', '-X', method or ('POST' if body is not None else 'GET'),
            'http://localhost:8083/' + path]
    if body is not None:
        args += ['-H', 'Content-Type: application/json', '--data-binary', '@-']
    output = docker(*args, stdin=None if body is None else json.dumps(body))
    return json.loads(output) if output else {}


def running():
    status = api('connectors/orders-outbox/status')
    return status.get('connector', {}).get('state') == 'RUNNING' and bool(status.get('tasks')) and all(
        task['state'] == 'RUNNING' for task in status['tasks'])


def insert(event_id, version):
    # Values are constants owned by this lab, not application input.
    sql(f"INSERT INTO outbox VALUES ('{event_id}', 'ord-42', 'order.changed', "
        f"'{{\"event_id\":\"{event_id}\",\"aggregate_version\":{version}}}');")

try:
    docker('network', 'create', network)
    docker('run', '-d', '--name', pg, '--network', network, '-e',
           'POSTGRES_PASSWORD=local-lab-only', 'postgres:17',
           '-c', 'wal_level=logical', '-c', 'max_replication_slots=4', timeout=240)
    containers.append(pg)
    wait_for(lambda: docker('exec', pg, 'pg_isready', '-U', 'postgres'), 'PostgreSQL ready')
    sql('CREATE TABLE outbox (event_id uuid PRIMARY KEY, aggregate_id text NOT NULL, '
        'event_type text NOT NULL, payload jsonb NOT NULL);')
    env = {
        'KAFKA_NODE_ID': '1', 'KAFKA_PROCESS_ROLES': 'broker,controller',
        'KAFKA_LISTENERS': 'PLAINTEXT://:9092,CONTROLLER://:9093',
        'KAFKA_ADVERTISED_LISTENERS': f'PLAINTEXT://{broker}:9092',
        'KAFKA_LISTENER_SECURITY_PROTOCOL_MAP': 'CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
        'KAFKA_CONTROLLER_LISTENER_NAMES': 'CONTROLLER',
        'KAFKA_CONTROLLER_QUORUM_VOTERS': f'1@{broker}:9093',
        'KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR': '1',
        'KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR': '1',
        'KAFKA_TRANSACTION_STATE_LOG_MIN_ISR': '1',
        'KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS': '0',
    }
    args = ['run', '-d', '--name', broker, '--network', network]
    for key, value in env.items(): args += ['-e', f'{key}={value}']
    docker(*args, 'apache/kafka:4.3.2', timeout=240)
    containers.append(broker)
    wait_for(lambda: docker('exec', broker, '/opt/kafka/bin/kafka-topics.sh',
        '--bootstrap-server', f'{broker}:9092', '--create', '--if-not-exists',
        '--topic', 'orders.events', '--partitions', '1', '--replication-factor', '1', timeout=20),
        'Kafka topic')
    args = ['run', '-d', '--name', connect, '--network', network]
    for key, value in {
        'BOOTSTRAP_SERVERS': f'{broker}:9092', 'GROUP_ID': 'cdc-lab',
        'CONFIG_STORAGE_TOPIC': 'cdc-configs', 'OFFSET_STORAGE_TOPIC': 'cdc-offsets',
        'STATUS_STORAGE_TOPIC': 'cdc-status', 'CONFIG_STORAGE_REPLICATION_FACTOR': '1',
        'OFFSET_STORAGE_REPLICATION_FACTOR': '1', 'STATUS_STORAGE_REPLICATION_FACTOR': '1',
        'OFFSET_FLUSH_INTERVAL_MS': '1000',
    }.items(): args += ['-e', f'{key}={value}']
    docker(*args, 'quay.io/debezium/connect:3.3', timeout=300)
    containers.append(connect)
    wait_for(lambda: api('connector-plugins'), 'Connect API')
    api('connectors', {'name': 'orders-outbox', 'config': {
        'connector.class': 'io.debezium.connector.postgresql.PostgresConnector',
        'database.hostname': pg, 'database.port': '5432', 'database.user': 'postgres',
        'database.password': 'local-lab-only', 'database.dbname': 'postgres',
        'topic.prefix': 'orders-db', 'plugin.name': 'pgoutput', 'slot.name': 'notes_outbox',
        'publication.name': 'notes_outbox', 'publication.autocreate.mode': 'filtered',
        'table.include.list': 'public.outbox', 'snapshot.mode': 'no_data',
        'key.converter': 'org.apache.kafka.connect.storage.StringConverter',
        'value.converter': 'org.apache.kafka.connect.json.JsonConverter',
        'value.converter.schemas.enable': 'false',
        'transforms': 'outbox', 'transforms.outbox.type': 'io.debezium.transforms.outbox.EventRouter',
        'transforms.outbox.table.field.event.id': 'event_id',
        'transforms.outbox.table.field.event.key': 'aggregate_id',
        'transforms.outbox.table.field.event.payload': 'payload',
        'transforms.outbox.route.by.field': 'event_type',
        'transforms.outbox.route.topic.replacement': 'orders.events',
        'transforms.outbox.table.expand.json.payload': 'true',
    }})
    wait_for(running, 'connector running')
    first, second = '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102'
    insert(first, 1)
    before = wait_for(lambda: api('connectors/orders-outbox/offsets').get('offsets'), 'stored source offset')
    api('connectors/orders-outbox/stop', method='PUT')
    wait_for(lambda: api('connectors/orders-outbox/status')['connector']['state'] == 'STOPPED', 'connector stopped')
    insert(second, 2)
    print('connector stopped: committed second event; outbox rows=' + sql('SELECT count(*) FROM outbox;'))
    api('connectors/orders-outbox/resume', method='PUT')
    wait_for(running, 'restarted connector')
    after = wait_for(lambda: (value if (value := api('connectors/orders-outbox/offsets').get('offsets'))
                     and value != before else None), 'advanced source offset')
    output = docker('exec', broker, '/opt/kafka/bin/kafka-console-consumer.sh',
        '--bootstrap-server', f'{broker}:9092', '--topic', 'orders.events', '--from-beginning',
        '--max-messages', '2', '--timeout-ms', '30000',
        '--formatter-property', 'print.key=true', '--formatter-property', 'print.headers=true', timeout=45)
    lines = output.splitlines()
    assert len(lines) == 2 and all('ord-42' in line for line in lines), output
    assert first in lines[0] and second in lines[1], output
    print('checkpoint before:', json.dumps(before, sort_keys=True))
    print('checkpoint after:', json.dumps(after, sort_keys=True))
    print(output)
    print('PASS: 2 ordered events, stable IDs and key, checkpoint advanced after outage')
except Exception:
    for name in containers:
        result = subprocess.run(['docker', 'logs', '--tail', '30', name], capture_output=True, text=True)
        print(name, result.stdout, result.stderr, flush=True)
    raise
finally:
    for name in reversed(containers):
        subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True)
    subprocess.run(['docker', 'network', 'rm', network], capture_output=True)

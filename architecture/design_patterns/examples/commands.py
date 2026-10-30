"""One plain command handler reached through HTTP-shaped and worker-shaped entry points."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Protocol


class InvalidCommand(Exception):
    pass


class NotAllowed(Exception):
    pass


class AlreadyExists(Exception):
    pass


@dataclass(frozen=True)
class StartInvestigation:
    investigation_id: str
    query: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.investigation_id, str)
            or not self.investigation_id.strip()
            or self.investigation_id != self.investigation_id.strip()
            or len(self.investigation_id) > 64
        ):
            raise InvalidCommand('invalid investigation identifier')
        if not isinstance(self.query, str) or not self.query.strip() or len(self.query) > 5000:
            raise InvalidCommand('invalid query')


@dataclass(frozen=True)
class Actor:
    """Trusted fixture context; real authentication/authorization resolution is outside this demo."""
    subject: str
    tenant_id: str
    permissions: frozenset[str]


@dataclass(frozen=True)
class AcceptedInvestigation:
    tenant_id: str
    investigation_id: str
    query: str


class InvestigationStore(Protocol):
    def accept(self, *, tenant_id: str, command: StartInvestigation) -> AcceptedInvestigation:
        """Create one record or reject the existing tenant/id pair; real implementations must be atomic."""
        ...


class MemoryStore:
    """Sequential fake only: not durable, thread-safe, or a database transaction model."""
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], AcceptedInvestigation] = {}
        self.calls = 0

    def accept(self, *, tenant_id: str, command: StartInvestigation) -> AcceptedInvestigation:
        self.calls += 1
        key = tenant_id, command.investigation_id
        if key in self.records:
            raise AlreadyExists('investigation already exists')
        result = AcceptedInvestigation(tenant_id, command.investigation_id, command.query)
        self.records[key] = result
        return result


def start_investigation(
    command: StartInvestigation, *, actor: Actor, store: InvestigationStore,
) -> AcceptedInvestigation:
    if not actor.tenant_id or 'investigations:create' not in actor.permissions:
        raise NotAllowed('investigation creation is not permitted')
    return store.accept(tenant_id=actor.tenant_id, command=command)


def parse_command(payload: object) -> StartInvestigation:
    if not isinstance(payload, dict) or set(payload) != {'investigation_id', 'query'}:
        raise InvalidCommand('expected investigation_id and query only')
    return StartInvestigation(payload['investigation_id'], payload['query'])


def http_entry(payload: object, *, actor: Actor, store: InvestigationStore) -> tuple[int, dict[str, str]]:
    try:
        command = parse_command(payload)
        accepted = start_investigation(command, actor=actor, store=store)
    except InvalidCommand:
        return 400, {'error': 'invalid_command'}
    except NotAllowed:
        return 403, {'error': 'not_allowed'}
    except AlreadyExists:
        return 409, {'error': 'already_exists'}
    return 201, {'investigation_id': accepted.investigation_id}


def worker_entry(envelope: object, *, actor: Actor, store: InvestigationStore) -> AcceptedInvestigation:
    if not isinstance(envelope, dict) or set(envelope) != {'schema_version', 'payload'}:
        raise InvalidCommand('invalid command envelope')
    if type(envelope['schema_version']) is not int or envelope['schema_version'] != 1:
        raise InvalidCommand('unsupported command schema')
    command = parse_command(envelope['payload'])
    return start_investigation(command, actor=actor, store=store)


def demo() -> None:
    actor = Actor('operator-1', 'acme', frozenset({'investigations:create'}))
    store = MemoryStore()
    status, body = http_entry(
        {'investigation_id': 'I-42', 'query': 'refund delay'}, actor=actor, store=store,
    )
    print(f'http: {status} {body["investigation_id"]}')
    accepted = worker_entry(
        {'schema_version': 1, 'payload': {'investigation_id': 'I-43', 'query': 'refund delay'}},
        actor=actor, store=store,
    )
    print(f'worker: accepted {accepted.investigation_id} for {accepted.tenant_id}')
    duplicate_status, _ = http_entry(
        {'investigation_id': 'I-42', 'query': 'refund delay'}, actor=actor, store=store,
    )
    print(f'duplicate: {duplicate_status}; stored records: {len(store.records)}')
    assert duplicate_status == 409 and len(store.records) == 2


def check_contracts() -> None:
    allowed = Actor('operator-1', 'acme', frozenset({'investigations:create'}))
    denied = Actor('viewer-1', 'acme', frozenset())
    store = MemoryStore()
    payload = {'investigation_id': 'I-42', 'query': 'refund delay'}
    assert http_entry(payload, actor=denied, store=store)[0] == 403
    assert store.calls == 0
    forged = {**payload, 'tenant_id': 'victim'}
    assert http_entry(forged, actor=allowed, store=store)[0] == 400
    assert store.calls == 0
    for invalid in ({'investigation_id': ' ', 'query': 'x'}, {'investigation_id': 'I-42', 'query': None}):
        assert http_entry(invalid, actor=allowed, store=store)[0] == 400
    assert store.calls == 0
    print('invalid input, forged context and denied callers reach no store operation')

    http_result = http_entry(payload, actor=allowed, store=store)
    other_store = MemoryStore()
    worker_result = worker_entry({'schema_version': 1, 'payload': payload}, actor=allowed, store=other_store)
    assert http_result == (201, {'investigation_id': 'I-42'})
    assert worker_result == store.records['acme', 'I-42']
    print('entry points produce the same application result in fresh stores')

    for version in (2, True, '1'):
        before = other_store.calls
        try:
            worker_entry({'schema_version': version, 'payload': payload}, actor=allowed, store=other_store)
        except InvalidCommand:
            pass
        else:
            raise AssertionError('unsupported schema accepted')
        assert other_store.calls == before
    print('unknown command schemas rejected before execution')

    try:
        worker_entry({'schema_version': 1, 'payload': payload}, actor=allowed, store=store)
    except AlreadyExists:
        pass
    else:
        raise AssertionError('duplicate was silently accepted')
    assert len(store.records) == 1
    other_tenant = Actor('operator-2', 'other', frozenset({'investigations:create'}))
    assert http_entry(payload, actor=other_tenant, store=store)[0] == 201
    assert set(store.records) == {('acme', 'I-42'), ('other', 'I-42')}
    print('duplicate policy and tenant-scoped identifiers verified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check_contracts() if args.check else demo()

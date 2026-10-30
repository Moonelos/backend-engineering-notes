"""Local construction/lifetime comparisons; run from the repository root."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class InvestigationRequest:
    query: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError('query must not be blank')
        if not self.evidence:
            raise ValueError('evidence must not be empty')
        if any(not item.strip() for item in self.evidence):
            raise ValueError('evidence items must not be blank')


class EvidenceBuilder:
    def __init__(self, query: str) -> None:
        self.query = query
        self._items: list[str] = []

    def add(self, item: str) -> None:
        self._items.append(item)

    def build(self) -> InvestigationRequest:
        return InvestigationRequest(query=self.query, evidence=tuple(self._items))


class ReportTemplate:
    """Template Method: run owns ordering; subclasses supply rendering."""
    def run(self, request: InvestigationRequest) -> str:
        heading = f'Investigation: {request.query}'
        body = self.render(request.evidence)
        return f'{heading}\n{body}'

    def render(self, evidence: tuple[str, ...]) -> str:
        raise NotImplementedError


class BulletReport(ReportTemplate):
    def render(self, evidence: tuple[str, ...]) -> str:
        return '\n'.join(f'- {item}' for item in evidence)


def render_report(
    request: InvestigationRequest,
    render: Callable[[tuple[str, ...]], str],
) -> str:
    heading = f'Investigation: {request.query}'
    return f'{heading}\n{render(request.evidence)}'


class LocalClient:
    """A lifetime probe, not an HTTP client or database pool."""
    def __init__(self) -> None:
        self.closed = False

    def read(self) -> str:
        if self.closed:
            raise RuntimeError('client is closed')
        return 'evidence'

    def close(self) -> None:
        self.closed = True


@contextmanager
def owned_client() -> Iterator[LocalClient]:
    client = LocalClient()
    try:
        yield client
    finally:
        client.close()


def main() -> None:
    direct = InvestigationRequest(query='refund delay', evidence=('source A',))
    builder = EvidenceBuilder('refund delay')
    builder.add('source A')
    first = builder.build()
    builder.add('source B')
    second = builder.build()
    assert direct == first
    assert first.evidence == ('source A',)
    assert second.evidence == ('source A', 'source B')
    print('builder: snapshots contain 1 then 2 sources; first stays unchanged')
    try:
        EvidenceBuilder('refund delay').build()
    except ValueError as error:
        print(f'invalid build: {error}')
    else:
        raise AssertionError('empty evidence was accepted')

    inherited = BulletReport().run(first)
    composed = render_report(first, lambda items: '\n'.join(f'- {x}' for x in items))
    assert inherited == composed == 'Investigation: refund delay\n- source A'
    print('template and composed function: identical report')

    with owned_client() as client:
        reader_a, reader_b = client, client
        assert reader_a is reader_b
        assert reader_a.read() == reader_b.read() == 'evidence'
    assert client.closed
    try:
        client.read()
    except RuntimeError as error:
        print(f'after scope: {error}')
    else:
        raise AssertionError('closed client stayed usable')
    try:
        with owned_client() as failed_client:
            raise ValueError('operation failed')
    except ValueError:
        assert failed_client.closed
        print('exception path: client closed')


if __name__ == '__main__':
    main()

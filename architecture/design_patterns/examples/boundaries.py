"""Local Adapter / Facade / Anti-Corruption Layer comparison."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Protocol


class ReviewStatus(Enum):
    PENDING = 'pending'
    REVIEWED = 'reviewed'


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    text: str
    confidence: float
    review_status: ReviewStatus


class InvalidVendorResponse(Exception):
    """The received representation cannot satisfy the evidence contract."""


class EvidenceUnavailable(Exception):
    """The known transport timeout prevented obtaining evidence."""


class VendorSearch(Protocol):
    def __call__(self, *, phrase: str) -> list[dict[str, object]]: ...


class EvidenceReader(Protocol):
    def __call__(self, query: str) -> tuple[Evidence, ...]: ...


STATUS_MAP = {2: ReviewStatus.PENDING, 7: ReviewStatus.REVIEWED}


def translate_record(record: dict[str, object]) -> Evidence:
    evidence_id = record.get('case_ref')
    text = record.get('snippet')
    score = record.get('confidence_bp')
    review_code = record.get('review_code')
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise InvalidVendorResponse('invalid evidence identifier')
    if not isinstance(text, str) or not text.strip():
        raise InvalidVendorResponse('invalid evidence text')
    if type(score) is not int or not 0 <= score <= 10_000:
        raise InvalidVendorResponse('invalid confidence basis points')
    if type(review_code) is not int or review_code not in STATUS_MAP:
        raise InvalidVendorResponse('unsupported review code')
    return Evidence(
        evidence_id=evidence_id,
        text=text,
        confidence=score / 10_000,
        review_status=STATUS_MAP[review_code],
    )


def read_vendor_evidence(query: str, *, search: VendorSearch) -> tuple[Evidence, ...]:
    try:
        records = search(phrase=query)
    except TimeoutError:
        raise EvidenceUnavailable('evidence lookup timed out') from None
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise InvalidVendorResponse('invalid evidence collection')
    return tuple(translate_record(row) for row in records)


def eligible(evidence: Evidence) -> bool:
    return evidence.review_status is ReviewStatus.REVIEWED and evidence.confidence >= 0.8


@dataclass(frozen=True)
class Preview:
    investigation_id: str
    evidence_ids: tuple[str, ...]


def preview_investigation(
    investigation_id: str, query: str, *, read: EvidenceReader,
) -> Preview:
    if not investigation_id.strip() or not query.strip():
        raise ValueError('investigation_id and query must be nonempty')
    candidates = read(query)
    return Preview(investigation_id, tuple(item.evidence_id for item in candidates if eligible(item)))


def fake_search(*, phrase: str) -> list[dict[str, object]]:
    # A deterministic, public fixture; no credentials or network call.
    if phrase != 'refund delay':
        return []
    return [
        {'case_ref': 'D-1', 'snippet': 'refund policy', 'confidence_bp': 9200, 'review_code': 7},
        {'case_ref': 'D-2', 'snippet': 'refund delay', 'confidence_bp': 9900, 'review_code': 2},
    ]


def demo() -> None:
    read = partial(read_vendor_evidence, search=fake_search)
    result = preview_investigation('I-42', 'refund delay', read=read)
    assert result == Preview('I-42', ('D-1',))
    print(f'preview: {result.investigation_id} -> {", ".join(result.evidence_ids)}')
    evidence = read('refund delay')[0]
    print(f'translation: 9200 -> {evidence.confidence}; 7 -> {evidence.review_status.value}')
    bad = {**fake_search(phrase='refund delay')[0], 'review_code': 99}
    try:
        translate_record(bad)
    except InvalidVendorResponse as error:
        print(f'unknown status rejected: {error}')
    else:
        raise AssertionError('unknown status accepted')


def check_contracts() -> None:
    first = fake_search(phrase='refund delay')[0]
    for patch in (
        {'review_code': 99}, {'review_code': True}, {'confidence_bp': True},
        {'confidence_bp': -1}, {'confidence_bp': 10_001},
        {'confidence_bp': 0.92}, {'case_ref': ''}, {'snippet': ''},
    ):
        try:
            translate_record({**first, **patch})
        except InvalidVendorResponse:
            pass
        else:
            raise AssertionError(f'invalid record accepted: {patch!r}')
    print('invalid values and unknown meanings rejected')
    for score, expected in ((0, 0.0), (8000, 0.8), (10_000, 1.0)):
        translated = translate_record({**first, 'confidence_bp': score})
        assert translated.confidence == expected
        assert eligible(translated) is (score >= 8000)
    assert not eligible(translate_record({**first, 'review_code': 2}))
    print('scale boundaries and reviewed-only eligibility verified')
    calls: list[str] = []

    def failing_search(*, phrase: str) -> list[dict[str, object]]:
        calls.append(phrase)
        raise TimeoutError('raw payload must not escape')

    try:
        read_vendor_evidence('refund delay', search=failing_search)
    except EvidenceUnavailable as error:
        assert str(error) == 'evidence lookup timed out'
        assert error.__suppress_context__
    else:
        raise AssertionError('timeout was not translated')
    assert calls == ['refund delay']
    print('known timeout translated without exposing vendor message')

    def alternate_reader(query: str) -> tuple[Evidence, ...]:
        return (Evidence('D-3', query, 0.85, ReviewStatus.REVIEWED),)

    assert preview_investigation('I-42', 'refund delay', read=alternate_reader).evidence_ids == ('D-3',)
    print('facade accepts a different reader without vendor fields')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check_contracts() if args.check else demo()

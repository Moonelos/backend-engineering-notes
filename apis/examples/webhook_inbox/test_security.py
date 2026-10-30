import pytest
from .webhook_security import sign_webhook, verify_webhook, VerificationError


def test_malformed_signature_and_valid_rotation_candidate():
    body = b'{"id":"evt_42"}'
    secret = b'local-test-only-' + b'x' * 32
    valid = sign_webhook(body=body, message_id='evt_42', timestamp=1000, secrets=[secret])
    args = dict(body=body, message_id='evt_42', timestamp='1000', secrets=[secret], now=1000)
    for malformed in ['v1,é', 'v1,@@@@', 'v1,eA==', 'v2,anything']:
        with pytest.raises(VerificationError):
            verify_webhook(signature_header=malformed, **args)
        verify_webhook(signature_header=malformed + ' ' + valid, **args)
    with pytest.raises(VerificationError):
        verify_webhook(signature_header=valid, **{**args, 'body': body + b' '})

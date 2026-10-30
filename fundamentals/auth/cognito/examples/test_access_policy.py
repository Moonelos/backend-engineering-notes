"""Real RSA signatures, in-process HTTP. No Cognito or JWKS network calls."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from access_policy import AccessPolicy, create_app

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_FIXTURE"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
POLICY = AccessPolicy(ISSUER, "serviceclient", frozenset({"myapi/read"}))


def signed(changes=None, remove=()):
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "serviceclient", "client_id": "serviceclient",
              "token_use": "access", "scope": "myapi/read", "iat": now, "exp": now + 300}
    claims.update(changes or {})
    for name in remove:
        claims.pop(name)
    return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "local-fixture"})


@pytest.mark.parametrize(("changes", "remove", "status"), [
    ({}, (), 200), ({"token_use": "id"}, (), 401), ({"client_id": "other"}, (), 401),
    ({"iss": "https://other.invalid"}, (), 401), ({"exp": 1}, (), 401),
    ({}, ("exp",), 401), ({"scope": "myapi/write"}, (), 403),
    ({"scope": ["myapi/read"]}, (), 401), ({"aud": "https://other.invalid"}, (), 401),
])
def test_m2m_http_boundary(changes, remove, status):
    with TestClient(create_app(POLICY, lambda token: KEY.public_key())) as client:
        response = client.get("/data", headers={"Authorization": "Bearer " + signed(changes, remove)})
    assert response.status_code == status


def test_missing_credential_and_tampered_signature():
    token = signed()
    h, p, s = token.split(".")
    token = ".".join((h, p, ("A" if s[0] != "A" else "B") + s[1:]))
    with TestClient(create_app(POLICY, lambda token: KEY.public_key())) as client:
        assert client.get("/data").status_code == 401
        assert client.get("/data", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_bound_user_profile_requires_exact_resource():
    policy = AccessPolicy(ISSUER, "serviceclient", frozenset({"myapi/read"}), "https://api.example.com")
    assert policy.validate(signed({"aud": "https://api.example.com"}), KEY.public_key())["token_use"] == "access"
    for token in [signed(), signed({"aud": "https://wrong.example.com"})]:
        with pytest.raises(jwt.InvalidTokenError):
            policy.validate(token, KEY.public_key())

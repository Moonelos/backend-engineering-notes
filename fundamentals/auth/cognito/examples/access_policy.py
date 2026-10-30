"""Canonical Cognito access policy; keys/issuer come from trusted configuration."""
from dataclasses import dataclass

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class InsufficientScope(jwt.InvalidTokenError):
    pass


@dataclass(frozen=True)
class AccessPolicy:
    issuer: str
    client_id: str
    required_scopes: frozenset[str]
    resource_audience: str | None = None

    def validate(self, token: str, signing_key) -> dict:
        required = ["exp", "iat", "iss", "sub", "token_use", "client_id", "scope"]
        if self.resource_audience is not None:
            required.append("aud")
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.resource_audience,
            options={"require": required,
                     "verify_aud": self.resource_audience is not None,
                     "strict_aud": True},
        )
        if claims["token_use"] != "access" or claims["client_id"] != self.client_id:
            raise jwt.InvalidTokenError("wrong token profile")
        if self.resource_audience is None and "aud" in claims:
            raise jwt.InvalidTokenError("unexpected resource-bound profile")
        if not isinstance(claims["scope"], str):
            raise jwt.InvalidTokenError("scope must be a space-separated string")
        if not self.required_scopes <= set(claims["scope"].split()):
            raise InsufficientScope("required scope absent")
        return claims


def jwks_key_resolver(issuer: str):
    # issuer is operator configuration, never read from an unverified JWT.
    client = jwt.PyJWKClient(issuer + "/.well-known/jwks.json", lifespan=300, timeout=5)

    def resolve(token: str):
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise jwt.InvalidTokenError("unsupported algorithm or missing key ID")
        return client.get_signing_key_from_jwt(token).key

    return resolve


def create_app(policy: AccessPolicy, resolve_key) -> FastAPI:
    app = FastAPI()
    bearer = HTTPBearer(auto_error=False)

    # Synchronous dependency: PyJWKClient's bounded HTTP fetch runs in a worker thread.
    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise HTTPException(401, "Bearer credential required", headers={"WWW-Authenticate": "Bearer"})
        try:
            token = credentials.credentials
            return policy.validate(token, resolve_key(token))
        except InsufficientScope:
            raise HTTPException(403, "Required scope absent") from None
        except jwt.PyJWKClientConnectionError:
            raise HTTPException(503, "Signing keys temporarily unavailable") from None
        except (jwt.InvalidTokenError, jwt.PyJWKClientError):
            raise HTTPException(401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}) from None

    @app.get("/data")
    def data(claims: dict = Depends(authorize)):
        return {"client": claims["client_id"], "items": []}

    return app

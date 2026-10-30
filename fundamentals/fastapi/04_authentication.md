# FastAPI Authentication & Security

<!-- length-justification: This is the canonical FastAPI authentication implementation reference; password handling, token issuance/validation, dependencies, OAuth flow, and complete application composition remain together so security-critical checks are not copied inconsistently. -->

> **Who this is for**: FastAPI engineers implementing identity verification and separate
> authorization decisions at HTTP boundaries.

> **Key insight**: Authentication proves identity; authorization separately decides whether that
> identity may perform the requested action.

This implementation reference assumes the [JWT and OAuth foundation](../auth/README.md).
The [local application and rejection tests](#first-result-a-complete-local-boundary) provide an executable
checkpoint; other fragments name the database/session integration they require.


## First result: a complete local boundary

The [application factory](examples/auth_app.py) supplies an actual in-memory directory, Argon2
password verification, JWT issuance/required-claim validation, public response projection, and a
path-bound post ownership dependency. The [executable tests](examples/auth_boundary_tests.py)
provide fixtures instead of a missing `get_user_by_email` implementation. From the repository root,
using the virtualenv created in the [Cognito guide](../auth/cognito/oauth-jwt-guide.md):

```bash
/tmp/cognito-notes-venv/bin/python -m pip install 'pwdlib[argon2]==0.3.0' 'bcrypt==5.0.0' 'httpcore==1.0.9' 'SQLAlchemy==2.1.6' 'aiosqlite==0.22.1'
/tmp/cognito-notes-venv/bin/python -m pytest -q fundamentals/fastapi/examples/auth_boundary_tests.py
```

The test logs in, calls `/users/me`, and checks that `hashed_password` and tenant fields are absent.
It updates an owned post and rejects `/posts/2?resource_id=1`: the guard reads the same `post_id` as
the route, so an extra query parameter cannot redirect authorization. Signed tokens missing `exp`,
with the wrong audience, expired, or labeled `refresh` receive 401. The companion tests cover the
API-security chapter's durable inbox and DNS pinning contracts.

This local application demonstrates the HTTP boundary; its in-memory directory is not durable and
its first-party login is not an OAuth authorization server. Use durable storage, account recovery,
rate limits, session/revocation policy, and a managed OAuth issuer in the production continuation.
HS256 assumes issuer and verifier share one trust boundary: a verifier holding the secret can mint
tokens. Across independent services, use the configured issuer's asymmetric JWKS policy taught in
[JWT](../auth/jwt.md) and [Cognito access tokens](../auth/cognito/tokens.md).

---

## 1. The Mental Model

### Authentication vs Authorization

These are **two separate concerns**. Mixing them is the root of most security bugs.

| Concept | Question | When | Example |
|---------|----------|------|---------|
| **Authentication (AuthN)** | Who are you? | Before anything else | Verify JWT, check password |
| **Authorization (AuthZ)** | What can you do? | After identity is established | Check role, verify ownership |

Authentication without authorization: "I know who you are, but I let you do anything."
Authorization without authentication: "I don't know who you are, but I'll check your permissions." (Nonsensical.)

> **Rule**: Authenticate first. Authorize second. Never combine them into one step.

---

### Tokens vs Sessions

Two fundamentally different strategies for maintaining identity across requests.

| Aspect | Session-Based | Token-Based (JWT) |
|--------|---------------|-------------------|
| **State** | Server stores session data | Client stores token |
| **Storage** | Server-side (Redis, DB) | Client-side (header, cookie) |
| **Scalability** | Requires shared session store | Stateless -- any server can validate |
| **Revocation** | Delete session from store | Hard -- token valid until expiry |
| **Size** | Small session ID | Larger (payload + signature) |
| **Use case** | Traditional web apps | APIs, SPAs, microservices |

### Stateless vs Stateful Auth

**Stateless** (JWT): The token itself contains everything needed to verify identity. No database lookup required on each request.

**Stateful** (Sessions): The server must look up session data on every request. More control, more infrastructure.

Self-contained bearer tokens fit multi-service and non-browser clients because an API can validate
them without a session lookup, but leakage remains effective until expiry and immediate revocation
needs extra state. Opaque tokens centralize introspection and revocation; server-side sessions fit
same-origin browser applications and can keep credentials in `HttpOnly` cookies. This guide focuses
on token-based APIs, not because they are universally standard, but because their validation and
authorization boundaries are the subject here.

---

## 2. Password Hashing

### Why Never Store Plaintext

If your database is breached and passwords are stored in plaintext, every user account is immediately compromised. This is not hypothetical -- it happens constantly.

**Hashing is one-way.** You can verify a password against a hash, but you cannot reverse the hash to get the password.

### The default pattern: `pwdlib` with Argon2

FastAPI's current tutorial uses `pwdlib` with Argon2. Argon2 is a memory-hard password hashing
algorithm, which raises the cost of large-scale guessing attacks.

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Hash a password for storage."""
    return password_hash.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash."""
    return password_hash.verify(plain_password, hashed_password)
```

**Compatibility alternative — direct `bcrypt`** (for systems already storing bcrypt hashes):

```python
import bcrypt


def hash_password(plain_password: str) -> str:
    """Compatibility hashing with explicit UTF-8 byte limit."""
    if len(plain_password.encode("utf-8")) > 72:
        raise ValueError("bcrypt input exceeds 72 bytes")
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash (constant-time comparison)."""
    if len(plain_password.encode("utf-8")) > 72:
        return False
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
```

> **bcrypt's 72-byte boundary:** bcrypt 5.0 raises `ValueError` above the limit; older
> implementations silently truncated. Count UTF-8 bytes, not characters. Preserve the legacy
> verification contract during migration and rehash successful logins into Argon2; do not silently
> change long-password interpretation. [bcrypt documentation](https://github.com/pyca/bcrypt),
> checked 2026-10-30. Bound request size and hashing concurrency even with Argon2.


### How It Works

```python
hashed = hash_password("my_secret_password")
# "$argon2id$v=19$..." (salt and hash vary each run)

verify_password("my_secret_password", hashed)   # True
verify_password("wrong_password", hashed)        # False
```

Key properties:
- **Salt is automatic** — the selected password hasher creates a fresh salt.
- **Comparison belongs to the library** — `password_hash.verify()` performs the algorithm's verification path.
- **Parameters can evolve** — `PasswordHash.recommended()` selects the current recommended scheme; store the encoded hash so its parameters travel with it.

### Common Mistakes

**Do not do this:**

```python
# WRONG -- storing plaintext
user.password = request.password

# WRONG -- using MD5 or SHA256 (fast hashes, easily brute-forced)
import hashlib
user.password = hashlib.sha256(request.password.encode()).hexdigest()
```

An attacker can measure tiny differences in an ordinary secret comparison and use repeated probes
to infer matching prefixes. Do not write an executable equality comparison for password-derived
secrets; call the password library's verifier, which owns the correct algorithm and comparison.

**Do this:**

```python
# CORRECT -- hash on registration
user.hashed_password = hash_password(request.password)

# CORRECT -- verify on login
if not verify_password(request.password, user.hashed_password):
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

---

## 3. JWT Tokens

### Structure

A signed compact JWT (JWS) has three Base64URL-encoded segments separated by dots:

```
header.payload.signature
```

| Part | Contains | Example |
|------|----------|---------|
| **Header** | Algorithm, token type | `{"alg": "HS256", "typ": "JWT"}` |
| **Payload** | Claims (user data, expiry) | `{"sub": "user@example.com", "exp": 1700000000}` |
| **Signature** | Cryptographic result over the encoded header and payload | HMAC for HS256; asymmetric signature for RS256/ES256 |

> **The payload is NOT encrypted.** Anyone can decode it. The signature only guarantees it hasn't been tampered with.

### Creating Tokens with PyJWT

> **Library baseline:** this path uses PyJWT 2.15.1 and `pwdlib`/Argon2, matching the
> [FastAPI tutorial's libraries](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
> Do not describe all `python-jose` versions as unmaintained or vulnerable: its 3.4.0 release fixed
> CVE-2024-33663/33664 and 3.5.0 followed. A migration must preserve required claims and algorithm
> policy, not just change imports. [Maintainer release notes](https://github.com/mpdavis/python-jose/releases).


```python
from datetime import datetime, timedelta, timezone
import jwt
from jwt import PyJWTError

import os
SECRET_KEY = os.environ["SECRET_KEY"]  # high-entropy secret, at least 32 bytes for HS256
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
TOKEN_ISSUER = "https://auth.example.com"
TOKEN_AUDIENCE = "https://api.example.com"


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc),
                      "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises PyJWTError on failure."""
    claims = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        issuer=TOKEN_ISSUER,
        audience=TOKEN_AUDIENCE,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "type"]},
    )
    if claims["type"] != "access":
        raise jwt.InvalidTokenError("Expected access token")
    return claims
```

### Token Expiration

**Every token must expire.** A token without expiration is a permanent credential.

```python
# Short-lived access token (15-30 minutes)
access_token = create_access_token(
    data={"sub": user.email},
    expires_delta=timedelta(minutes=30),
)

# PyJWT automatically rejects expired tokens (raises ExpiredSignatureError)
try:
    payload = decode_access_token(token)
except PyJWTError:
    raise HTTPException(status_code=401, detail="Token invalid or expired")
```

### Refresh tokens: a separate stateful credential

Do not feed a refresh token to the access-token decoder. The access policy requires an API audience
and `type=access`; a refresh credential belongs only at the authorization server. Prefer a managed
issuer's supported rotation. If building a first-party session service, use a high-entropy opaque
refresh token and store only its hash with a family, expiry and consumed state.

The complete [refresh concurrency fixture](../auth/examples/refresh_rotation.py) and
[transaction explanation](../auth/jwt.md#revocation-and-refresh-token-rotation) are the canonical
implementation model. A refresh operation locks the family, re-reads the token under that lock,
consumes it and inserts one successor in one transaction. Reuse commits family revocation before
returning an error. Two unlocked reads followed by a repository `rotate()` call are insufficient.

```mermaid
sequenceDiagram
    participant Client
    participant Auth as Refresh endpoint
    participant DB as Family transaction
    Client->>Auth: Opaque refresh credential in protected body or cookie
    Auth->>DB: Lock family and re-read token hash
    alt Unused and unexpired
        DB->>DB: Consume predecessor and insert successor atomically
        DB-->>Auth: Commit successor metadata
        Auth-->>Client: Access token plus replacement refresh token
    else Reused
        DB->>DB: Commit family revocation
        Auth-->>Client: 401 and require fresh login
    end
```

The transaction makes one successor possible, not guaranteed delivery of the HTTP response. Define
lost-response behavior and serialize refreshes per client session. Browser cookies need `Secure`,
`HttpOnly`, an appropriate `SameSite` policy **and CSRF protection**; native apps use platform secure
storage. Never put refresh tokens in a query string. Short access expiry bounds exposure only when
the API has no immediate revocation check.

---

## 4. Bearer extraction and the legacy password-form example

### What It Does

`OAuth2PasswordBearer` is a FastAPI class that:
1. Declares a token URL for the OpenAPI docs (Swagger UI "Authorize" button)
2. Extracts the `Bearer` token from the `Authorization` header
3. Returns the raw token string

It does **NOT** validate the token. That is your job.

### The Login Flow

This form example explains FastAPI's tutorial compatibility interface. It is not a recommendation
to introduce the OAuth resource-owner password grant: published security guidance prohibits that
grant. Use Authorization Code + PKCE for new OAuth user clients, as taught in
[OAuth](../auth/oauth2.md). The complete local fixture later uses a first-party JSON login solely to
exercise hashing, issuance and HTTP policy in one process.

```python
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


# Simulated user lookup -- replace with real DB query
def authenticate_user(email: str, password: str):
    user = get_user_by_email(email)  # your DB lookup
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}
```

### How the Flow Works

```
1. Client sends POST /auth/login with username + password (form data)
2. Server validates credentials
3. Server returns {"access_token": "eyJ...", "token_type": "bearer"}
4. Client sends subsequent requests with header: Authorization: Bearer eyJ...
5. oauth2_scheme extracts "eyJ..." from the header
```

> **Note**: `OAuth2PasswordRequestForm` expects `username` and `password` as **form fields**, not JSON. This is the OAuth2 spec. Your "username" field can contain an email -- the field name is just `username`.

---

## 5. Dependency-Based Auth

This is where FastAPI's dependency injection system makes auth elegant. You build a chain of dependencies that authenticate and authorize in clean, composable layers.

> This section assumes familiarity with the DI patterns in [02_dependency_injection.md](./02_dependency_injection.md) — sub-dependencies, caching per request, and `Depends(...)` composition. The code below focuses on the JWT/auth-specific wiring only; the DI mechanics are identical.

### The `get_current_user` Dependency

```python
from pydantic import BaseModel


class User(BaseModel):
    id: str
    tenant_id: str
    email: str
    is_active: bool
    role: str  # "user", "admin", "moderator"


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception

    user = get_user_by_email(email)  # your DB lookup
    if user is None:
        raise credentials_exception
    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user
```

### Using It in Endpoints

```python
class UserPublic(BaseModel):
    id: str
    email: str


@app.get("/users/me", response_model=UserPublic)
def read_current_user(user: User = Depends(get_current_active_user)):
    return user


@app.get("/users/me/orders")
def read_my_orders(user: User = Depends(get_current_active_user)):
    return get_orders_for_user(user.email)
```

### Role-Based Authorization

```python
from functools import wraps
from typing import Callable


def require_role(required_role: str) -> Callable:
    """Dependency factory that checks user role."""
    def role_checker(user: User = Depends(get_current_active_user)) -> User:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return user
    return role_checker


@app.get("/admin/dashboard")
def admin_dashboard(user: User = Depends(require_role("admin"))):
    return {"message": f"Welcome admin {user.email}"}


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_role("admin"))):
    # Only admins can delete users
    return {"deleted": user_id}
```

### Permission Guards (Fine-Grained)

For more granular control than roles:

```python
def require_permissions(*permissions: str) -> Callable:
    """Check that user has ALL required permissions."""
    def permission_checker(user: User = Depends(get_current_active_user)) -> User:
        user_permissions = get_user_permissions(user)  # your lookup
        missing = set(permissions) - set(user_permissions)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {missing}",
            )
        return user
    return permission_checker


@app.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    user: User = Depends(require_permissions("posts:delete")),
):
    return {"deleted": post_id}
```

### The Dependency Chain

```
oauth2_scheme          → extracts token from header
    ↓
get_current_user       → decodes token, fetches user (AuthN)
    ↓
get_current_active_user → checks user is active
    ↓
require_role("admin")   → checks user role (AuthZ)
```

Each layer has **one responsibility**. Each can be tested independently. Each can be overridden in tests.

---

## 6. CORS (Cross-Origin Resource Sharing)

### What It Is

CORS controls whether browser JavaScript can read a cross-origin response. For requests requiring
preflight, the browser first asks permission with OPTIONS and sends the actual request only when
allowed. A simple request can already reach the server and change state before the browser hides
its response. CORS is neither authentication nor CSRF protection, and it does not constrain curl or
another server. [Browser CORS behavior](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).

```mermaid
sequenceDiagram
    participant Browser
    participant API
    Browser->>API: OPTIONS asking for Authorization and PUT
    API-->>Browser: Explicit allowed origin method and headers
    Browser->>API: PUT with bearer credential
    API->>API: Authenticate and authorize object mutation
    API-->>Browser: Response with CORS headers
```

Successful preflight permits the browser to send the request; it does not authorize the operation.
Investigate OPTIONS and actual-request logs separately. Cookie authentication also needs a CSRF
strategy even when an untrusted origin cannot read the response.

### FastAPI CORSMiddleware

```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com", "https://staging.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### Configuration Reference

| Parameter | Purpose | Recommendation |
|-----------|---------|----------------|
| `allow_origins` | Which origins can call the API | List specific domains |
| `allow_credentials` | Allow browser credentialed responses such as cookies | Enable for cross-origin cookie/credentials mode; a manually supplied bearer header separately needs `allow_headers` |
| `allow_methods` | Which HTTP methods | List only what you use |
| `allow_headers` | Which request headers | List only what you need |
| `expose_headers` | Which response headers the browser can read | As needed |
| `max_age` | How long to cache preflight responses (seconds) | `600` (10 minutes) |

### Common CORS Mistakes

**Do not do this:**

```python
# Inappropriate for a policy restricted to the trusted browser application.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # A wildcard response origin cannot authorize credentialed reads.
    allow_methods=["*"],
    allow_headers=["*"],
)
```

A wildcard response origin cannot authorize a credentialed browser read. Wildcard origins can be
appropriate for intentionally public, noncredentialed data; production alone does not decide that.
For authenticated browser sessions, configure explicit origins and test actual browser behavior.
A malicious site does not gain the user's bearer token merely because an API permits its origin,
and CORS rejection does not guarantee that a simple state-changing request was never sent.

**Do this:**

```python
# CORRECT -- explicit origins
import os

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # ["https://app.example.com"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### Development vs Production

```python
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "development":
    origins = ["http://localhost:3000", "http://localhost:5173"]
else:
    origins = ["https://app.example.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 7. API Key Authentication

### When to Use API Keys

| Auth Method | Use Case |
|-------------|----------|
| JWT + OAuth2 | User-facing APIs, SPAs, mobile apps |
| API Keys | Service-to-service, third-party integrations, machine clients |

API keys are simpler but less flexible. They identify a **client**, not a **user**.

### Header-Based API Key Dependency

```python
import hashlib
import secrets

from fastapi import Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key")


def get_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    key_id, separator, secret_value = api_key.partition(".")
    record = get_api_key_record(key_id) if separator else None
    candidate_digest = hashlib.sha256(secret_value.encode()).digest()

    # The public key ID bounds the lookup; only fixed-size digests are compared.
    if record is None or not secrets.compare_digest(candidate_digest, record.secret_digest):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return key_id


@app.get("/external/data")
def get_data(api_key: str = Depends(get_api_key)):
    return {"data": "sensitive information"}
```

### API Key with Client Identification

```python
class APIClient(BaseModel):
    name: str
    permissions: list[str]
    rate_limit: int


def get_api_client(api_key: str = Security(API_KEY_HEADER)) -> APIClient:
    """Resolve API key to a client with permissions and rate limits."""
    client = lookup_client_by_key(api_key)  # your DB lookup
    if not client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return client


@app.get("/partner/orders")
def get_partner_orders(client: APIClient = Depends(get_api_client)):
    if "orders:read" not in client.permissions:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return get_orders_for_client(client.name)
```

### Supporting Both JWT and API Key

```python
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user_or_client(
    token: str | None = Depends(oauth2_scheme),
    api_key: str | None = Security(api_key_header),
) -> User | APIClient:
    """Accept either JWT or API key authentication."""
    principal = None
    if token:
        principal = decode_and_get_user(token)  # Full JWT profile plus active user lookup.
    elif api_key:
        principal = lookup_client_by_key(api_key)  # Hashed key lookup; only active clients.
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
        )
    return principal
```

---

## 8. Security Headers

### HTTPS Enforcement

**Never run production without HTTPS.** JWTs sent over HTTP can be intercepted trivially.

FastAPI itself does not handle TLS. Your reverse proxy (Nginx, Caddy, a load balancer) terminates TLS. But you can enforce HTTPS redirect:

```python
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

# Only in production -- breaks local development
if ENVIRONMENT == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

### Trusted Host Middleware

Prevent host header attacks:

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.example.com", "*.example.com"],
)
```

### Common Security Headers

Add security headers via middleware:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"  # obsolete browser filter; disable
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)
```

### Security Headers Reference

| Header | Purpose | Value |
|--------|---------|-------|
| `X-Content-Type-Options` | Prevent MIME-type sniffing | `nosniff` |
| `X-Frame-Options` | Prevent clickjacking | `DENY` |
| `Strict-Transport-Security` | Force HTTPS | `max-age=31536000; includeSubDomains` |
| `Referrer-Policy` | Control referrer information | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Restrict browser features | Disable unused APIs |

---

## 9. Common Patterns

### Protecting Routes

```python
# Protected by default -- requires valid token
@app.get("/users/me", response_model=UserPublic)
def get_me(user: User = Depends(get_current_active_user)):
    return user


# Protected at router level -- all routes in this router require auth
admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(require_role("admin"))],
)

@admin_router.get("/stats")
def admin_stats():
    # User is already verified as admin by router dependency
    return get_system_stats()

@admin_router.delete("/users/{user_id}")
def admin_delete_user(user_id: int):
    return delete_user(user_id)

app.include_router(admin_router)
```

### Optional Authentication

Some endpoints work for both authenticated and anonymous users:

```python
def get_optional_user(
    token: str | None = Depends(OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)),
) -> User | None:
    """Returns user if authenticated, None otherwise."""
    if token is None:
        return None
    try:
        payload = decode_access_token(token)
        email = payload.get("sub")
        if email is None:
            return None
        return get_user_by_email(email)
    except PyJWTError:
        return None


@app.get("/posts/{post_id}")
def get_post(post_id: int, user: User | None = Depends(get_optional_user)):
    post = get_post_by_id(post_id)
    if user:
        post.is_liked = check_user_liked(user.email, post_id)
    return post
```

### Resource Ownership Check

```python
def get_own_resource(post_id: int, user: User = Depends(get_current_active_user)):
    """Verify user owns the resource they're trying to access."""
    resource = get_resource_by_id(post_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.owner_email != user.email and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your resource")
    return resource


@app.put("/posts/{post_id}")
def update_post(body: PostUpdate, resource=Depends(get_own_resource)):
    return update_post_in_db(resource, body)
```

### Rate Limiting Per User

```python
from collections import defaultdict
from datetime import datetime, timezone

# Simple in-memory rate limiter (use Redis in production)
request_counts: dict[str, list[datetime]] = defaultdict(list)


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
):
    def limiter(user: User = Depends(get_current_active_user)) -> User:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)

        # Clean old entries
        request_counts[user.email] = [
            t for t in request_counts[user.email] if t > window_start
        ]

        if len(request_counts[user.email]) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

        request_counts[user.email].append(now)
        return user

    return limiter


@app.post("/api/expensive-operation")
def expensive_op(user: User = Depends(rate_limit(max_requests=10, window_seconds=60))):
    return perform_expensive_operation(user)
```

---

## 10. Common Mistakes

### Storing Secrets in Code

```python
# WRONG -- secret in source code
SECRET_KEY = "super-secret-key-12345"
DATABASE_URL = "postgresql://user:password@host/db"
```

```python
# CORRECT -- from environment
import os

SECRET_KEY = os.environ["SECRET_KEY"]  # Fails loudly if missing
DATABASE_URL = os.environ["DATABASE_URL"]
```

Or with Pydantic Settings:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str
    database_url: str
    allowed_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_file": ".env"}


settings = Settings()
```

---

### Not Validating Token Expiry

An unsafe decoder disables expiry verification through an option such as `verify_exp=False`.
Keep that shape as inert text: making it executable invites it to survive copy/paste.

```python
# Reuse the complete access profile from section 2.
payload = decode_access_token(token)
# Missing exp/iat/iss/aud/sub/type, expired tokens, wrong issuer/audience,
# and refresh tokens all raise PyJWTError.
```

---

### Overly Permissive CORS

```python
# WRONG -- any origin, all methods, all headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

```python
# CORRECT -- explicit whitelist
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

### Leaking Information in Error Messages

```python
# WRONG -- tells attacker which field is wrong
if not user:
    raise HTTPException(status_code=401, detail="User not found")
if not verify_password(password, user.hashed_password):
    raise HTTPException(status_code=401, detail="Wrong password")
```

```python
# CORRECT -- same error for both cases
if not user or not verify_password(password, user.hashed_password):
    raise HTTPException(status_code=401, detail="Incorrect email or password")
```

---

### Using `auto_error=True` When You Need Optional Auth

```python
# WRONG -- returns 401 for unauthenticated users on public endpoints
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")  # auto_error=True by default

@app.get("/public-feed")
def public_feed(token: str = Depends(oauth2_scheme)):
    # Anonymous users get 401 -- but this should be public!
    ...
```

```python
# CORRECT -- auto_error=False for optional auth
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

@app.get("/public-feed")
def public_feed(token: str | None = Depends(oauth2_scheme_optional)):
    user = decode_user_from_token(token) if token else None
    return get_feed(user=user)
```

---

### Not Setting Token Type in Refresh Tokens

```python
# WRONG -- access and refresh tokens are interchangeable
def create_access_token(data: dict) -> str:
    return jwt.encode({**data, "exp": ...}, SECRET_KEY)

def create_refresh_token(data: dict) -> str:
    return jwt.encode({**data, "exp": ...}, SECRET_KEY)
# Attacker can use a refresh token as an access token!
```

```python
# CORRECT -- tokens have explicit types
def create_access_token(data: dict) -> str:
    return jwt.encode({**data, "exp": ..., "type": "access"}, SECRET_KEY)

def create_refresh_token(data: dict) -> str:
    return jwt.encode({**data, "exp": ..., "type": "refresh"}, SECRET_KEY)

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    ...
```

---

### Missing Rate Limiting on Auth Endpoints

```python
# WRONG -- no rate limiting on login
@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Attacker can brute-force passwords at full speed
    ...
```

Auth endpoints (login, register, password reset) should **always** be rate-limited. Use a reverse proxy (Nginx, Cloudflare) or application-level rate limiting.

---

## 11. Production Checklist

| Concern | Action |
|---------|--------|
| **Secrets** | Load from environment variables, never from code |
| **Passwords** | Hash with bcrypt (direct) or argon2 via `pwdlib`, never store plaintext; avoid unmaintained `passlib` |
| **JWTs** | Set expiration, validate on every request, use token types |
| **CORS** | Explicit origins for credentialed browser access; wildcard only for intentionally public noncredentialed responses |
| **HTTPS** | Enforce via reverse proxy, add HSTS header |
| **Error messages** | Never leak whether a user exists or which field is wrong |
| **Rate limiting** | Protect login and registration endpoints |
| **Dependencies** | Build auth as composable dependency chains |
| **Headers** | Add security headers via middleware |
| **Refresh tokens** | Store securely, distinguish from access tokens, rotate and detect reuse |

---


---

## Key Principles

1. **Auth is a dependency chain** -- each layer has one job
2. **Tokens are not encrypted** -- they are signed; never put secrets in the payload
3. **Passwords must be hashed** -- bcrypt (direct) or argon2, never a fast hash; avoid the unmaintained `passlib`
4. **CORS governs browser reads** -- configure it for the application's origin and credential model; retain authentication and CSRF controls
5. **Secrets come from the environment** -- never from source code
6. **Errors should not leak information** -- same message for wrong user and wrong password
7. **Every token must expire** -- a token without expiry is a permanent key


## Retention and transfer

**Recap:** authenticate with a complete token policy, fetch current account state when required,
then authorize the operation and exact resource. Filter public responses explicitly.

**Check yourself:** a valid signature has no expiry claim. Will `jwt.decode` necessarily reject it?
<details><summary>Answer</summary>No. Expiry verification checks a present claim; the endpoint must
also require `exp`. The local negative fixture proves the distinction.</details>

**Try it:** add a second tenant whose user has the same display email as an existing user. Design
the stable subject and resource lookup, then test a cross-tenant post ID.
<details><summary>Answer</summary>Use an immutable user ID scoped by the issuer, bind tenant context
from trusted membership, and include both tenant and object in the query. Neither display email
nor a role alone grants cross-tenant ownership.</details>

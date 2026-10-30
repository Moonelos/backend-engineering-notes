# Environment & Configuration in Python — A Production Guide

<!-- length-justification: This is the canonical configuration reference; source precedence, typed validation, secrets, framework wiring, and deployment examples remain together because they form one startup boundary whose order must not drift. -->

> **Who this is for**: Python backend developers who know environment variables
> and want one typed, validated configuration boundary for local development,
> tests, containers, and production secret delivery.

> **Key insight**: Treat deployment strings as untrusted input at one typed startup boundary.

This guide explains **how to manage configuration in Python backend applications** — from local development to production. It covers the 12-factor app methodology (a set of practices for deployable services), pydantic-settings, secrets management, and real-world patterns for FastAPI.

> **Mental model**: deployment sources provide untrusted strings; one Settings
> object parses and validates them at startup; the rest of the application
> consumes typed, immutable-by-policy values.

---

## 1. The Core Principle: Config Belongs in the Environment

The [12-factor app](https://12factor.net/config) methodology defines one rule for configuration.
Here, **environment** means the deployment-provided boundary outside the built artifact: environment
variables, mounted files, or a secret/configuration service.

> **Everything that changes between deploys (dev, staging, prod) must be supplied outside the code artifact.**

This includes:

- Database URLs
- API keys and secrets
- Feature flags
- Debug mode
- External service endpoints
- Port numbers, worker counts

### Why This Matters

```python
# ❌ Config in code — must redeploy to change anything
DATABASE_URL = "postgresql://user:pass@prod-db:5432/myapp"
STRIPE_KEY = "example-not-a-real-key"
DEBUG = False
```

```python
# ✅ Config from environment — same code runs everywhere
import os
DATABASE_URL = os.environ["DATABASE_URL"]
STRIPE_KEY = os.environ["STRIPE_KEY"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
```

The second version can run in dev, staging, and prod **without any code changes**. The environment provides the values.

### The Problem with `os.environ`

Raw `os.environ` works but has real issues:

- No type conversion — everything is a string
- No centralized validation — direct lookups fail whenever executed, including startup; parsing and validation must be assembled manually
- No defaults — manual `.get()` everywhere
- No documentation — you discover required vars by reading code
- No nesting — flat namespace only

This is where pydantic-settings comes in.

---

## 2. pydantic-settings — Typed Configuration

`pydantic-settings` gives you validated, typed, documented configuration using Pydantic models.

```bash
pip install pydantic-settings
```

### Basic Settings Class

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379"
    debug: bool = False
    api_key: str
    max_connections: int = 10
```

### How It Works

`BaseSettings` reads values from **environment variables** automatically:

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/myapp"
export API_KEY="example-not-a-real-key"
```

```python
settings = Settings()
print(settings.database_url)  # postgresql://user:pass@localhost:5432/myapp
print(settings.debug)         # False (default)
print(settings.max_connections)  # 10 (default)
```

### Resolution Order

pydantic-settings resolves its default non-CLI sources in this order (first
match wins):

| Priority | Source              | Example                              |
| -------- | ------------------- | ------------------------------------ |
| 1        | Init kwargs         | `Settings(debug=True)`               |
| 2        | Environment vars    | `export DEBUG=true`                  |
| 3        | `.env` file         | `DEBUG=true` in `.env`               |
| 4        | Secrets directory   | `/run/secrets/api_key`               |
| 5        | Field default       | `debug: bool = False`                |

If no source provides a required value, constructing Settings fails. Construct it eagerly during startup to fail before serving; a lazy dependency postpones the same failure until first use.

CLI parsing and custom settings sources can change this order. If precedence
matters, test it explicitly rather than relying on memory.

---

## Follow one schema from local values to the serving process

The canonical runnable path is [settings_lab.py](examples/settings_lab.py). It keeps one `Settings` shape throughout: `environment`, `debug`, nested `database` (`url`, positive `pool_size`) and nested `auth` (`secret_key`, nonsecret `version`). Both nested models and the root are frozen. The local `CredentialClient` captures the selected key/version to make consumer lifetime observable; it does not claim to connect to a real database or identity provider.

Install the declared dependencies in a disposable environment and run its complete staged experiment:

```bash
python3 -m venv /tmp/notes-settings-venv
/tmp/notes-settings-venv/bin/python -m pip install 'pydantic-settings>=2,<3' 'fastapi>=0.162,<0.163' 'uvicorn>=0.30,<1' 'httpx>=0.28,<0.29'
/tmp/notes-settings-venv/bin/python fundamentals/core_concepts/runtime/examples/settings_probe.py
```

The fixture creates matching `database` and `auth` secret filenames containing JSON for those nested fields, plus a `.env` file. It runs these changes in order:

1. `.env` says `DEBUG=false`, while the environment says `true`; environment wins. An explicit `Settings(debug=False)` wins over both.
2. The first app starts with credential label v7. Replacing the file with v8 changes neither the cached settings nor the captured client's v7 label.
3. The lifespan closes the old client, the fixture clears the settings cache, and a new app constructs a v8 client. Clearing the cache alone would not update the old client.
4. A higher-priority `AUTH__VERSION` still masks the file's version. Rotation must inspect source precedence as well as freshness.
5. `DATABASE__POOL_SIZE=0` fails in lifespan before requests can be served. Diagnostics are asserted not to contain the fixture key.

The expected final `PASS` identifies precedence, cached v7, closed client and restarted v8. The probe uses an actual ASGI lifespan and health endpoint. HTTPX-backed TestClient may emit the documented newer Starlette deprecation warning; it is a compatibility baseline for this fixture.

```mermaid
flowchart LR
 I[Init kwargs] --> P[Resolve each field by priority]
 E[Environment] --> P
 D[Dotenv file] --> P
 S[Mounted files] --> P
 P --> V[Settings parses and validates]
 V --> C[Process-owned cached snapshot]
 C --> A[Construct dependent client before serving]
 V --> F[Invalid input: startup fails]
```

The arrows end at a snapshot and a client, not live bindings to the files. The process must own replacement and close/drain ordering. Each process has its own snapshot. The remainder of sections 3–8 is a reference of alternative settings shapes and source options; do not concatenate those independent `Settings` definitions into the canonical file.

## 3. `.env` Files

### Loading `.env` Files

Configure your settings class to read from `.env`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str
    redis_url: str = "redis://localhost:6379"
    debug: bool = False
    api_key: str
```

`env_file=".env"` is resolved from the process's current working directory.
pydantic-settings does not walk parent directories looking for it. Start the
application from a defined working directory or pass an explicit path from the
entry point.

### `.env` File Format

```bash
# .env — local development only
DATABASE_URL=postgresql://user:pass@localhost:5432/myapp
REDIS_URL=redis://localhost:6379
API_KEY=example-not-a-real-key
DEBUG=true
```

### The `.env.example` Pattern

Your `.env` file contains real secrets — it must never be committed. Instead, commit a `.env.example` that documents every variable:

```bash
# .env.example — committed to git, documents all config vars
DATABASE_URL=postgresql://user:pass@localhost:5432/myapp
REDIS_URL=redis://localhost:6379
API_KEY=your-api-key-here
DEBUG=true
```

New developers clone the repo, copy `.env.example` to `.env`, and fill in real values:

```bash
cp .env.example .env
# edit .env with real credentials
```

### .gitignore Rules

```gitignore
# ❌ NEVER commit these
.env
.env.local
.env.production

# ✅ ALWAYS commit these
.env.example
```

---

## 4. Settings Validation

### Type Coercion

pydantic-settings automatically converts environment variable strings to Python types:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = False          # "true" → True, "1" → True, "false" → False
    port: int = 8000             # "8000" → 8000
    rate_limit: float = 1.5      # "1.5" → 1.5
    allowed_hosts: list[str] = ["localhost"]  # '["localhost","example.com"]' → list
    workers: int | None = None   # unset → None
```

### Required vs Optional

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — no default, startup fails if missing
    database_url: str
    secret_key: str

    # Optional with defaults
    debug: bool = False
    port: int = 8000

    # Optional, can be None
    sentry_dsn: str | None = None
    redis_url: str | None = None
```

> `Optional[X]` and `X | None` are equivalent in Python 3.10+. This Python 3.11+
> corpus prefers the modern `X | None` spelling for new code; see
> [../typing/typing.md](../typing/typing.md#2-nullable-values--prefer-x--none).

### Custom Validators

```python
from pydantic import field_validator

class Settings(BaseSettings):
    database_url: str
    port: int = 8000
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1024 <= v <= 65535):
            raise ValueError("Port must be between 1024 and 65535")
        return v
```

### Validation at Startup

A missing field or failed validator raises when Settings is constructed. The canonical lifespan below calls the loader eagerly; merely declaring a cached dependency would defer validation to the first request:

```
pydantic_core._pydantic_core.ValidationError: 2 validation errors for Settings
database_url
  Field required [type=missing, input_value={}, input_type=dict]
secret_key
  Field required [type=missing, input_value={}, input_type=dict]
```

---

## 5. Nested Settings

For large applications, group related config into nested models:

```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseModel):
    url: str
    pool_size: int = 5
    pool_timeout: int = 30
    echo: bool = False

class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379"
    ttl: int = 3600

class AuthSettings(BaseModel):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",   # enables SECTION__KEY format
    )

    environment: str = "development"
    debug: bool = False
    database: DatabaseSettings
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings
```

With `env_nested_delimiter="__"`, set nested values like:

```bash
DATABASE__URL=postgresql://user:pass@localhost:5432/myapp
DATABASE__POOL_SIZE=20
DATABASE__ECHO=true
REDIS__URL=redis://prod-redis:6379
REDIS__TTL=7200
AUTH__SECRET_KEY=super-secret-key
AUTH__ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=production
```

Access them cleanly:

```python
settings = Settings()
settings.database.url          # "postgresql://..."
settings.database.pool_size    # 20
settings.auth.secret_key       # "super-secret-key"
```

---

## 6. The Singleton Pattern — `@lru_cache`

Settings should be loaded **once** and reused. Creating a new `Settings()` instance on every request re-reads environment variables and `.env` files needlessly.

```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Why `@lru_cache`

| Approach            | Reads env | Parses `.env` | Validates | Per call |
| ------------------- | --------- | ------------- | --------- | -------- |
| `Settings()` direct | Yes       | Yes           | Yes       | Every time |
| `@lru_cache`        | Once      | Once          | Once      | Cached   |

### Usage in FastAPI with Dependency Injection

```python
from functools import lru_cache
from fastapi import Depends, FastAPI
from contextlib import asynccontextmanager

@lru_cache
def get_settings() -> Settings:
    return Settings()

@asynccontextmanager
async def lifespan(app):
    get_settings()  # Validate before serving, not on the first request.
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/info")
def info(settings: Settings = Depends(get_settings)):
    return {
        "environment": settings.environment,
        "debug": settings.debug,
    }
```

This gives you:

- **Singleton** — settings loaded once, reused across all requests
- **Testable** — override via `app.dependency_overrides[get_settings]`
- **Explicit** — every endpoint declares its dependency on config

### Testing with Overrides

```python
from fastapi.testclient import TestClient


def get_test_settings() -> Settings:
    return Settings(
        environment="test",
        debug=True,
        database={"url": "sqlite:///test.db"},
        auth={"secret_key": "test-secret"},
    )


def test_info_uses_override() -> None:
    app.dependency_overrides[get_settings] = get_test_settings
    try:
        with TestClient(app) as client:
            response = client.get("/info")
        assert response.status_code == 200
        assert response.json()["debug"] is True
    finally:
        app.dependency_overrides.pop(get_settings, None)
```

When a test changes environment variables and calls `get_settings()` directly,
clear the cache before and after the assertion:

```python
def test_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE__URL", "sqlite:///test.db")
    monkeypatch.setenv("AUTH__SECRET_KEY", "test-secret")
    monkeypatch.setenv("DEBUG", "true")
    get_settings.cache_clear()
    try:
        assert get_settings().debug is True
    finally:
        get_settings.cache_clear()
```

Environment changes after the first cached call do not update the existing
object. That stability is desirable in production; use explicit cache clearing
only in tests or a deliberately designed reload mechanism.

---

## 7. Environment-Specific Configuration

### The `ENVIRONMENT` Variable

Use a single variable to identify the deployment environment:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    environment: str = "development"    # development | staging | production
    debug: bool = False
    database_url: str
    log_level: str = "INFO"
```

```bash
# Development
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql://user:pass@localhost:5432/myapp_dev
LOG_LEVEL=DEBUG

# Production
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://user:pass@prod-db:5432/myapp
LOG_LEVEL=INFO
```

### Computed Properties Based on Environment

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    environment: str = "development"
    debug: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
```

A plain property is intentional: `computed_field` includes the value in model
serialization, while these booleans are conveniences derived from real settings,
not additional configuration.

Usage:

```python
settings = get_settings()

if settings.is_production:
    sentry_sdk.init(dsn=settings.sentry_dsn)

if settings.is_development:
    app = FastAPI(docs_url="/docs")
else:
    app = FastAPI(docs_url=None)  # disable docs in prod
```

Disabling interactive docs may reduce accidental exposure, but it is not access
control. Protect the application and any schema endpoint with network and
authentication policy appropriate to the deployment.

### Per-Environment `.env` Files

```python
class Settings(BaseSettings):
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),  # .env.local overrides .env
    )
```

---

## 8. Secrets Management

### Why the artifact is the wrong secret boundary

A secret committed once remains in git history after the current file is cleaned. A secret copied
into a Docker layer remains recoverable from the image even if a later layer deletes it. Environment
variables may appear in process diagnostics and platform inspection APIs, while mounted files may be
read by any process with sufficient filesystem permission. These exposure paths are why delivery and
access controls belong to the deployment platform.

> **Secrets must never exist in your codebase, your git history, or your Docker images.**

### Development: `.env` File

In development, `.env` is fine for secrets — just keep it out of git:

```bash
# .env (local dev only, in .gitignore)
DATABASE_URL=postgresql://dev:dev@localhost:5432/myapp
SECRET_KEY=not-a-real-secret
STRIPE_KEY=example-not-a-real-key
```

### Production: Environment Variables or Mounted Secrets

In production, secrets come from the platform — not files in your repo:

| Platform         | How secrets are provided             |
| ---------------- | ------------------------------------ |
| Docker / K8s     | Environment vars or mounted files    |
| AWS ECS          | Secrets Manager → env vars           |
| Railway / Render | Dashboard → env vars                 |
| Vault            | API call at startup or sidecar       |

Environment variables are convenient but can appear in process diagnostics,
crash reports, or platform inspection APIs. Mounted secret files reduce some of
that exposure and can support rotation, but their permissions and lifecycle
still need controls. Kubernetes Secret values are not made confidential merely
by base64 encoding; configure encryption at rest and role-based access control (RBAC), the policy
that limits which cluster identities may read a Secret.

#### Kubernetes Secrets as Environment Variables

```yaml
# k8s deployment
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: myapp-secrets
        key: database-url
  - name: SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: myapp-secrets
        key: secret-key
```

#### Kubernetes Secrets as Mounted Files

```yaml
volumes:
  - name: secrets
    secret:
      secretName: myapp-secrets
      items:
        - key: database-url
          path: database_url
        - key: secret-key
          path: secret_key
volumeMounts:
  - name: secrets
    mountPath: /run/secrets
    readOnly: true
```

pydantic-settings can read from secrets files:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        secrets_dir="/run/secrets",
    )

    database_url: str
    secret_key: str
```

With `secrets_dir`, pydantic-settings reads `/run/secrets/database_url` as the value for `database_url`.

### `SecretStr` — Keep Secrets Out of Logs and Tracebacks

A plain `str` secret can leak when a settings object is printed, logged, or
serialized. Pydantic's `SecretStr` masks its normal string representation and
requires an explicit unwrap at the point of use:

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: SecretStr
    stripe_key: SecretStr | None = None


settings = Settings()
print(settings.secret_key)                 # SecretStr('**********')
print(repr(settings))                      # secret_key=SecretStr('**********')
print(settings.secret_key.get_secret_value())  # the real value — only when you ask
```

Use `SecretStr` for every credential (`secret_key`, API keys, DB passwords).
Call `.get_secret_value()` only at the point of use — e.g. when building a
connection or signing a token — never when logging.

`SecretStr` is defense in depth, not automatic leak prevention. A caller can
unwrap it, a connection URL can contain it, and raw environment input can appear
outside the model. Keep secrets out of log fields and sanitize exception paths.

### What Not to Do

```text
# ❌ Hardcoded secret
SECRET_KEY = "my-super-secret-key-12345"

# ❌ Secret in default value
class Settings(BaseSettings):
    api_key: str = "example-not-a-real-key"

# ❌ Secret in committed .env
# (if .env is not in .gitignore)

# ❌ Secret in Docker image
COPY .env /app/.env

# ❌ Secret in git history
# (even if you deleted the file, it's still in history)
```

---

## 9. Launch the same validated app

Use the same [settings_lab.py](examples/settings_lab.py), not a new settings schema. From the repository root, run:

```bash
ENVIRONMENT=production DEBUG=false \
DATABASE__URL='sqlite:///fixture.db' AUTH__SECRET_KEY='fake-local-only' AUTH__VERSION=v7 \
/tmp/notes-settings-venv/bin/python -m uvicorn settings_lab:create_app --factory \
  --app-dir fundamentals/core_concepts/runtime/examples --host 127.0.0.1 --port 18081
```

In another terminal:

```bash
curl --fail --silent http://127.0.0.1:18081/health
```

Expect `status: ok`, `environment: production`, `debug: false` and `credential_version: v7`; no database URL or key is returned. Stop with Ctrl-C so Uvicorn drives lifespan cleanup. Launch again with `DATABASE__POOL_SIZE=0`: startup must fail and health must never become ready. All supplied credentials are fake local data; this experiment validates configuration/lifetime, not external authentication.

The app factory defers construction until lifespan, which calls the loader before yielding readiness. It stores the resulting snapshot and dependent client together, then closes the client in `finally`. For real rotation, drain requests using the old client before closing it, validate the replacement and prove target authentication. A process restart is often the simplest explicit reload policy.

The canonical nested mount uses files named `database` and `auth`, each containing JSON for that field. The earlier flat reference uses `database_url` and `secret_key`; Kubernetes `items.path` maps hyphenated Secret keys to those exact filenames. A mount is not inferred from an unrelated environment variable spelling. Keep dotenv files out of source control, use safe `.env.example` placeholders and validate the actual deployment's source precedence.

---

## 10. Common Patterns

### Database URL

```python
from pydantic import SecretStr
from sqlalchemy import URL


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: SecretStr
    db_name: str = "myapp"

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
```

`URL.create()` handles reserved characters in usernames/passwords correctly and
masks the password in its normal string representation. Pass the `URL` object
directly to SQLAlchemy. If a driver requires a string, unwrap/render it only at
that integration boundary. Do not log the rendered credential URL.

Choose one canonical input shape: either a complete deployment-provided **data
source name (DSN)** connection string or
separate components. Defining both creates precedence and consistency problems.

### Feature Flags

```python
class Settings(BaseSettings):
    enable_signups: bool = True
    enable_dark_mode: bool = False
    enable_beta_features: bool = False
    max_upload_size_mb: int = 10
```

Environment-backed booleans are deployment flags. They are appropriate for
coarse switches that change only on restart. Use a real feature-flag service for
live rollouts, per-user targeting, audit history, or rapid rollback.

```python
@app.post("/signup")
def signup(settings: Settings = Depends(get_settings)):
    if not settings.enable_signups:
        raise HTTPException(status_code=403, detail="Signups are disabled")
    ...
```

### CORS Origins

Cross-Origin Resource Sharing (CORS) governs browser access to cross-origin responses and preflight
permission for certain requests. Simple cross-origin requests can still be sent; CORS is neither
authorization nor CSRF protection.

```python
class Settings(BaseSettings):
    cors_origins: list[str] = ["http://localhost:3000"]
```

```bash
CORS_ORIGINS='["http://localhost:3000","https://myapp.com"]'
```

### Debug Mode Guard

```python
@app.get("/debug/config")
def debug_config(settings: Settings = Depends(get_settings)):
    if not settings.debug:
        raise HTTPException(status_code=404)
    # Never expose secrets — even in debug mode
    return {
        "environment": settings.environment,
        "debug": settings.debug,
        "log_level": settings.log_level,
        "features": {
            "signups": settings.enable_signups,
            "webhooks": settings.enable_webhooks,
        },
    }
```

---

## 11. Common Mistakes

### Hardcoded secrets

```python
# ❌ Secret in source code
JWT_SECRET = "my-jwt-secret-key"

# ✅ Secret from environment
class Settings(BaseSettings):
    jwt_secret: str   # no default — required from env
```

### Missing `.env` in `.gitignore`

```python
# ❌ .env committed to git — secrets in history forever
# Even deleting the file later doesn't remove it from history

# ✅ Add .env to .gitignore BEFORE your first commit
```

### Mutable global settings

```python
# ❌ Mutable — any code can corrupt config at runtime
settings = {"debug": True, "db_url": "..."}
settings["debug"] = False  # someone does this somewhere

# ✅ Frozen Pydantic model — immutable after creation
class Settings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True)
    debug: bool = False
```

`frozen=True` is shallow with respect to nested objects. Freeze nested Pydantic
models too, and avoid mutable containers when the complete settings tree must
remain unchanged.

### Creating settings per request

```python
# ❌ Re-reads env + .env on every single request
@app.get("/items")
def items():
    settings = Settings()   # expensive and unnecessary
    ...

# ✅ Cached singleton via @lru_cache
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Using `os.environ` directly alongside pydantic-settings

```python
# ❌ Mixed approaches — config scattered across two systems
class Settings(BaseSettings):
    database_url: str

settings = get_settings()
debug = os.environ.get("DEBUG", "false")  # why not in Settings?

# ✅ All config in one place
class Settings(BaseSettings):
    database_url: str
    debug: bool = False
```

### Secrets in default values

```python
# ❌ Default value is a real secret — ends up in git
class Settings(BaseSettings):
    api_key: str = "example-not-a-real-key"

# ✅ No default for secrets — force them from environment
class Settings(BaseSettings):
    api_key: str   # required, no default
```

---

## 12. Quick Reference

### Startup Checklist

1. All secrets come from deployment-provided environment or secret files (never code)
2. `.env` is in `.gitignore`
3. `.env.example` documents every variable
4. Settings class validates types and constraints
5. `@lru_cache` prevents repeated loading
6. FastAPI accesses settings via `Depends(get_settings)`
7. No `os.environ` calls scattered through business logic

### Settings Class Template

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        env_ignore_empty=True,
        frozen=True,
        hide_input_in_errors=True,
    )

    environment: str = "development"
    debug: bool = False

    # Add your config fields here

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Key Decisions Table

| Decision                      | Development           | Production                   |
| ----------------------------- | --------------------- | ---------------------------- |
| Secrets source                | `.env` file           | Platform env vars / secrets  |
| Debug mode                    | `True`                | `False`                      |
| `.env` file                   | Exists, gitignored    | Not used (env vars instead)  |
| Log level                     | `DEBUG`               | `INFO` by default; tune noisy loggers/handlers |
| Docs endpoint                 | Usually `/docs`        | Protect or disable by deployment policy |
| Settings validation           | Same as prod          | Same as dev                  |
| `@lru_cache` settings         | Yes                   | Yes                          |

---


## Recap

- Validate once at an explicit startup boundary before clients and readiness.
- Source precedence, cached object lifetime and dependent client lifetime are separate.
- Secret masking complements safe diagnostic fields; it does not revoke credentials.

## Check yourself

**Q: The secret file contains v8, but /health still reports client v7. Is the mount necessarily broken?**

<details><summary>Answer</summary>

No. The settings object and client may be snapshots. Drain/close the old client, reconstruct settings and clients under the chosen restart/reload policy, then prove target authentication.

</details>

**Q: Does a cached Depends(get_settings) alone prove startup validation?**

<details><summary>Answer</summary>

No. It is lazy. Lifespan must call the loader before yielding readiness.

</details>

## Try it

Change the fixture to provide AUTH__VERSION from the environment while rotating the auth file. Predict the restarted label.

Hint: Environment has higher priority than files.

<details><summary>Worked solution</summary>

The restarted label remains the environment value until that override is removed; cache clearing cannot change precedence.

</details>

**Next**: [Logging basics](logging/01_basics.md), then the logging path and [signals](signals.md). Readers who already own logging lifetime can continue directly to signals.

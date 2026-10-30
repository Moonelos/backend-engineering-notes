"""One startup settings snapshot and its dependent client. Python 3.11+."""
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    url: SecretStr
    pool_size: int = Field(default=5, ge=1, le=100)

class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    secret_key: SecretStr
    version: str  # Safe deployment label, not a credential or a token.

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8',
        env_nested_delimiter='__', frozen=True, hide_input_in_errors=True, extra='forbid')
    environment: Literal['development', 'test', 'production'] = 'development'
    debug: bool = False
    database: DatabaseSettings
    auth: AuthSettings

@lru_cache
def get_settings() -> Settings:
    return Settings()

class CredentialClient:
    """Local stand-in: captures credential state; never performs network authentication."""
    def __init__(self, settings: Settings):
        self.version = settings.auth.version
        self._key = settings.auth.secret_key
        self.closed = False
    async def close(self):
        self.closed = True
        self._key = None

def create_app(loader=get_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        settings = loader()  # Eager validation before readiness or any request.
        client = CredentialClient(settings)
        app.state.settings, app.state.client = settings, client
        try:
            yield
        finally:
            await client.close()
    app = FastAPI(lifespan=lifespan)
    @app.get('/health')
    def health():
        settings = app.state.settings
        return {'status': 'ok', 'environment': settings.environment, 'debug': settings.debug,
                'credential_version': app.state.client.version}
    return app

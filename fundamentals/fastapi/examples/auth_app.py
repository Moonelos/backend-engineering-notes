"""Local authentication boundary. In-memory fixtures are not a production directory."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field
from pwdlib import PasswordHash

ISSUER = "https://auth.example.com"
AUDIENCE = "https://api.example.com"


@dataclass
class UserRecord:
    id: str
    email: str
    tenant_id: str
    hashed_password: str
    is_active: bool = True


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str = Field(min_length=1, max_length=1024)


class PostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


def encode_access(secret: str, subject: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": subject, "iat": now, "exp": now + timedelta(minutes=15),
                       "iss": ISSUER, "aud": AUDIENCE, "type": "access"}, secret, algorithm="HS256")


def decode_access(secret: str, token: str) -> dict:
    claims = jwt.decode(token, secret, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE,
                        options={"require": ["sub", "iat", "exp", "iss", "aud", "type"]})
    if claims["type"] != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def create_app(secret: str, users: dict[str, UserRecord], posts: dict[int, dict]) -> FastAPI:
    if len(secret.encode()) < 32:
        raise ValueError("HS256 requires a high-entropy secret of at least 32 bytes")
    app = FastAPI()
    passwords = PasswordHash.recommended()
    dummy_hash = passwords.hash("local-dummy-timing-input")
    bearer = HTTPBearer(auto_error=False)

    def active_user(credential: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credential is None:
            raise HTTPException(401, "Invalid credentials")
        try:
            claims = decode_access(secret, credential.credentials)
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid credentials") from None
        user = users.get(claims["sub"])
        if user is None or not user.is_active:
            raise HTTPException(401, "Invalid credentials")
        return user

    @app.post("/login")
    def login(body: Login):
        user = next((u for u in users.values() if u.email == body.email), None)
        valid = passwords.verify(body.password, user.hashed_password if user else dummy_hash)
        if not valid or user is None or not user.is_active:
            raise HTTPException(401, "Invalid credentials")
        return {"access_token": encode_access(secret, user.id), "token_type": "bearer"}

    @app.get("/users/me", response_model=UserPublic)
    def me(user: UserRecord = Depends(active_user)):
        return user

    def own_post(post_id: int, user: UserRecord = Depends(active_user)):
        post = posts.get(post_id)
        if post is None or post["tenant_id"] != user.tenant_id or post["owner_id"] != user.id:
            raise HTTPException(404, "Post not found")
        return post

    @app.put("/posts/{post_id}")
    def update_post(body: PostUpdate, post: dict = Depends(own_post)):
        post["title"] = body.title
        return {"id": post["id"], "title": post["title"]}

    return app

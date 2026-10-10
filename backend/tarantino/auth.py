"""Admin login: one password from the environment, a signed session cookie.

Without TARANTINO_ADMIN_PASSWORD the admin stays open (and says so), so a fresh
installation can never lock its owner out.
"""

import asyncio
import hashlib
import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from tarantino.services import Services, get_services

COOKIE = "tarantino_admin"
SESSION_SECONDS = 90 * 24 * 3600


def _sign(secret: bytes, value: str) -> str:
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def make_token(secret: bytes, now: float | None = None) -> str:
    issued = str(int(now if now is not None else time.time()))
    return f"{issued}.{_sign(secret, issued)}"


def token_valid(secret: bytes, token: str | None, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    issued, signature = token.split(".", 1)
    if not issued.isdigit() or not hmac.compare_digest(signature, _sign(secret, issued)):
        return False
    return (now if now is not None else time.time()) - int(issued) < SESSION_SECONDS


def password_configured(services: Services) -> bool:
    return services.settings_env.admin_password is not None and bool(services.settings_env.admin_password.get_secret_value())


def require_admin(request: Request, services: Annotated[Services, Depends(get_services)]) -> None:
    if not password_configured(services):
        return
    if not token_valid(services.secret, request.cookies.get(COOKIE)):
        raise HTTPException(status_code=401, detail="Login required")


router = APIRouter(prefix="/api/admin", tags=["auth"])


class Login(BaseModel):
    password: str


@router.get("/session")
def session(request: Request, services: Annotated[Services, Depends(get_services)]) -> dict:
    configured = password_configured(services)
    return {
        "password_set": configured,
        "authenticated": not configured or token_valid(services.secret, request.cookies.get(COOKIE)),
    }


@router.post("/login")
async def login(body: Login, response: Response, services: Annotated[Services, Depends(get_services)]) -> dict:
    if not password_configured(services):
        return {"authenticated": True}
    expected = services.settings_env.admin_password.get_secret_value()
    if not hmac.compare_digest(body.password.encode(), expected.encode()):
        await asyncio.sleep(1)  # slow down guessing
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(
        COOKIE, make_token(services.secret), max_age=SESSION_SECONDS, httponly=True, samesite="lax", path="/"
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}

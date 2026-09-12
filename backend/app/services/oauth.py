"""Minimal OAuth authorization-code + PKCE support for IMAP access."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import settings

_LOCK = Lock()
_FLOWS: dict[str, dict] = {}
FLOW_TTL_SECONDS = 10 * 60

PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email https://mail.google.com/",
    },
    "microsoft": {
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "openid email offline_access https://outlook.office.com/IMAP.AccessAsUser.All",
    },
}


class OAuthError(RuntimeError):
    pass


def _client(provider: str) -> tuple[str, str]:
    if provider == "google":
        return settings.google_oauth_client_id, settings.google_oauth_client_secret
    if provider == "microsoft":
        return settings.microsoft_oauth_client_id, settings.microsoft_oauth_client_secret
    return "", ""


def callback_url(provider: str) -> str:
    return f"{settings.public_backend_url}/api/mail/oauth/{provider}/callback"


def is_configured(provider: str) -> bool:
    client_id, client_secret = _client(provider)
    if provider == "google":
        return bool(client_id and client_secret)
    return bool(client_id)


def start_flow(provider: str, email: str, days: int) -> tuple[str, str]:
    if provider not in PROVIDERS:
        raise OAuthError("Unsupported OAuth provider")
    client_id, _ = _client(provider)
    if not is_configured(provider):
        env_names = (
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET"
            if provider == "google"
            else "MICROSOFT_OAUTH_CLIENT_ID"
        )
        raise OAuthError(f"OAuth is not configured; set {env_names} in .env")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    with _LOCK:
        _purge_expired()
        _FLOWS[state] = {
            "provider": provider,
            "email": email,
            "days": days,
            "verifier": verifier,
            "created": time.time(),
        }
    params = {
        "client_id": client_id,
        "redirect_uri": callback_url(provider),
        "response_type": "code",
        "scope": PROVIDERS[provider]["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "login_hint": email,
    }
    if provider == "google":
        params.update({"access_type": "offline", "prompt": "consent"})
    return f"{PROVIDERS[provider]['authorize']}?{urlencode(params)}", state


def take_flow(state: str, provider: str) -> dict:
    with _LOCK:
        flow = _FLOWS.pop(state, None)
    if (
        not flow
        or flow["provider"] != provider
        or time.time() - flow["created"] > FLOW_TTL_SECONDS
    ):
        raise OAuthError("OAuth request is missing, expired, or invalid")
    return flow


def exchange_code(provider: str, code: str, flow: dict) -> str:
    client_id, client_secret = _client(provider)
    payload = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": callback_url(provider),
        "grant_type": "authorization_code",
        "code_verifier": flow["verifier"],
    }
    if client_secret:
        payload["client_secret"] = client_secret
    request = Request(
        PROVIDERS[provider]["token"],
        data=urlencode(payload).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError("The provider did not complete the token exchange") from exc
    token = body.get("access_token")
    if not token:
        raise OAuthError("The provider response did not contain an access token")
    return str(token)


def _purge_expired() -> None:
    cutoff = time.time() - FLOW_TTL_SECONDS
    for state in [key for key, value in _FLOWS.items() if value["created"] < cutoff]:
        _FLOWS.pop(state, None)

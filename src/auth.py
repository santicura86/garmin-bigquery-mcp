"""Garmin auth.

- interactive_login(): email + password + MFA, local only. Writes the local token file.
- upload_local_tokens(): pushes the local token file to Secret Manager (scripts/export_tokens.sh).
- restore_session(): token-only login from the latest Secret Manager version (local + CI).
- persist_refreshed_tokens(): writes tokens back to Secret Manager if the library refreshed them.
"""
import getpass
import json
import logging
import os

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)
from google.api_core import exceptions as gexc
from google.cloud import secretmanager

from src.config import (
    GARMIN_TOKEN_DIR,
    GARMIN_TOKEN_FILE,
    GCP_PROJECT_ID,
    TOKENS_EXPIRED_MSG,
    TOKENS_SECRET,
    TOKENS_VERSIONS_TO_KEEP,
)

log = logging.getLogger(__name__)

_SECRET_PATH = f"projects/{GCP_PROJECT_ID}/secrets/{TOKENS_SECRET}"


class TokensExpiredError(RuntimeError):
    pass


# --- Secret Manager ----------------------------------------------------------

def _sm() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


def _read_latest_tokens() -> str:
    try:
        resp = _sm().access_secret_version(name=f"{_SECRET_PATH}/versions/latest")
    except gexc.NotFound as e:
        raise TokensExpiredError(f"No Garmin tokens in Secret Manager. {TOKENS_EXPIRED_MSG}") from e
    return resp.payload.data.decode("utf-8")


def _write_tokens(tokens: str) -> None:
    """Add a new secret version, then prune: keep the newest N, older ones destroyed."""
    sm = _sm()
    new = sm.add_secret_version(parent=_SECRET_PATH, payload={"data": tokens.encode("utf-8")})
    log.info("Saved Garmin tokens to Secret Manager (%s)", new.name.rsplit("/", 1)[-1])
    versions = sorted(
        (v for v in sm.list_secret_versions(parent=_SECRET_PATH)
         if v.state != secretmanager.SecretVersion.State.DESTROYED),
        key=lambda v: int(v.name.rsplit("/", 1)[-1]),
        reverse=True,
    )
    for i, v in enumerate(versions):
        if v.name == new.name:
            continue
        if i >= TOKENS_VERSIONS_TO_KEEP:
            sm.destroy_secret_version(name=v.name)
        elif v.state == secretmanager.SecretVersion.State.ENABLED:
            sm.disable_secret_version(name=v.name)


def _write_local_token_file(tokens: str) -> None:
    GARMIN_TOKEN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(GARMIN_TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tokens)


# --- Public API ----------------------------------------------------------------

def interactive_login() -> Garmin:
    """Log in with email + password + MFA and save tokens locally. Never used in CI."""
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    api = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    GARMIN_TOKEN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    api.login(str(GARMIN_TOKEN_DIR))  # library writes garmin_tokens.json (0600)
    if not GARMIN_TOKEN_FILE.exists():
        raise RuntimeError(f"Login succeeded but no tokens were written to {GARMIN_TOKEN_DIR}")
    return api


def upload_local_tokens() -> None:
    """Push the local token file (from `login`) to Secret Manager as the new latest version."""
    if not GARMIN_TOKEN_FILE.exists():
        raise TokensExpiredError(f"No local tokens at {GARMIN_TOKEN_FILE}; run `garmin_sync.py login` first.")
    _write_tokens(GARMIN_TOKEN_FILE.read_text(encoding="utf-8"))


def restore_session() -> tuple[Garmin, str]:
    """Token-only login from Secret Manager. No password fallback, ever.

    Returns the API and the token JSON it started from (for persist_refreshed_tokens).
    """
    tokens = _read_latest_tokens()
    _write_local_token_file(tokens)
    api = Garmin()  # no email/password: the library cannot fall back to credential login
    try:
        api.login(str(GARMIN_TOKEN_DIR))
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        raise TokensExpiredError(TOKENS_EXPIRED_MSG) from e
    persist_refreshed_tokens(api, tokens)  # login() may already have refreshed proactively
    return api, api.client.dumps()


def persist_refreshed_tokens(api: Garmin, previous: str) -> str:
    """If the library refreshed tokens since `previous`, save them to Secret Manager."""
    current = api.client.dumps()
    if json.loads(current) != json.loads(previous):
        _write_tokens(current)
    return current

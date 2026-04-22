"""Token discovery and refresh logic."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from .notify import prompt_sso_login

log = logging.getLogger("aws-sso-keepalive")

REFRESH_BUFFER_MINUTES = 15


def get_sso_cache_dir() -> Path:
    return Path.home() / ".aws" / "sso" / "cache"


def parse_expiry(expiry_str: str) -> datetime:
    expiry_str = expiry_str.replace("Z", "+00:00")
    return datetime.fromisoformat(expiry_str)


def find_refreshable_tokens(cache_dir: Path) -> list[dict]:
    tokens = []
    if not cache_dir.exists():
        log.warning("SSO cache directory not found: %s", cache_dir)
        return tokens

    for f in cache_dir.glob("*.json"):
        if f.name.startswith("aws-toolkit") or f.name.startswith("kiro"):
            continue
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        if "refreshToken" in data and "accessToken" in data:
            data["_cache_file"] = str(f)
            tokens.append(data)

    return tokens


def token_needs_refresh(token: dict) -> bool:
    try:
        expires_at = parse_expiry(token["expiresAt"])
    except (KeyError, ValueError):
        return False
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    return remaining < REFRESH_BUFFER_MINUTES * 60


def refresh_token(token: dict) -> bool:
    region = token.get("region", "us-east-1")
    cache_file = Path(token["_cache_file"])
    client = boto3.client("sso-oidc", region_name=region)

    try:
        response = client.create_token(
            clientId=token["clientId"],
            clientSecret=token["clientSecret"],
            grantType="refresh_token",
            refreshToken=token["refreshToken"],
        )
    except (
        client.exceptions.InvalidClientException,
        client.exceptions.InvalidGrantException,
        client.exceptions.UnauthorizedClientException,
        client.exceptions.ExpiredTokenException,
    ):
        prompt_sso_login(token.get("startUrl", "unknown"))
        return False
    except Exception as e:
        log.error("Failed to refresh token: %s", e)
        return False

    token["accessToken"] = response["accessToken"]
    token["expiresAt"] = (
        datetime.now(timezone.utc)
        .fromtimestamp(time.time() + response["expiresIn"], tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    if "refreshToken" in response:
        token["refreshToken"] = response["refreshToken"]

    write_data = {k: v for k, v in token.items() if not k.startswith("_")}
    cache_file.write_text(json.dumps(write_data, indent=2))

    log.info(
        "Refreshed token for %s (new expiry: %s)",
        token.get("startUrl", "unknown"),
        token["expiresAt"],
    )
    return True


def refresh_all() -> int:
    cache_dir = get_sso_cache_dir()
    tokens = find_refreshable_tokens(cache_dir)

    if not tokens:
        log.info("No refreshable SSO tokens found in cache.")
        return 0

    refreshed = 0
    for token in tokens:
        start_url = token.get("startUrl", "unknown")

        # Skip tokens that expired long ago (>1 hour) — their refresh token is likely dead
        try:
            expires_at = parse_expiry(token["expiresAt"])
            expired_seconds = (datetime.now(timezone.utc) - expires_at).total_seconds()
            if expired_seconds > 3600:
                log.debug("Skipping stale token for %s (expired %.0f hours ago).", start_url, expired_seconds / 3600)
                continue
        except (KeyError, ValueError):
            pass

        if token_needs_refresh(token):
            log.info("Token for %s is expiring soon, refreshing...", start_url)
            if refresh_token(token):
                refreshed += 1
        else:
            try:
                expires_at = parse_expiry(token["expiresAt"])
                remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
                log.info(
                    "Token for %s is still valid (%.0f min remaining).",
                    start_url,
                    remaining / 60,
                )
            except (KeyError, ValueError):
                pass

    return refreshed

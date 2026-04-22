import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aws_sso_keepalive import refresh


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(cache_dir, name, payload):
    path = cache_dir / name
    path.write_text(json.dumps(payload))
    return path


def test_token_needs_refresh_boundary():
    now = datetime.now(timezone.utc)
    inside_buffer = {"expiresAt": _iso(now + timedelta(minutes=5))}
    outside_buffer = {"expiresAt": _iso(now + timedelta(minutes=30))}
    malformed = {"expiresAt": "not-a-date"}

    assert refresh.token_needs_refresh(inside_buffer) is True
    assert refresh.token_needs_refresh(outside_buffer) is False
    assert refresh.token_needs_refresh(malformed) is False


def test_find_refreshable_tokens_filters_and_skips(tmp_path):
    valid = {
        "accessToken": "a",
        "refreshToken": "r",
        "expiresAt": _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
    }
    _write(tmp_path, "valid.json", valid)
    _write(tmp_path, "aws-toolkit-vscode.json", valid)
    _write(tmp_path, "kiro-auth-token.json", valid)
    _write(tmp_path, "no-refresh.json", {"accessToken": "a", "expiresAt": "x"})
    (tmp_path / "malformed.json").write_text("{not json")

    tokens = refresh.find_refreshable_tokens(tmp_path)

    assert len(tokens) == 1
    assert tokens[0]["_cache_file"].endswith("valid.json")


def test_refresh_all_skips_stale_tokens(tmp_path):
    long_expired = {
        "accessToken": "a",
        "refreshToken": "r",
        "startUrl": "https://example.awsapps.com/start",
        "expiresAt": _iso(datetime.now(timezone.utc) - timedelta(hours=2)),
    }
    _write(tmp_path, "stale.json", long_expired)

    with patch.object(refresh, "get_sso_cache_dir", return_value=tmp_path), \
         patch.object(refresh, "refresh_token") as do_refresh:
        count = refresh.refresh_all()

    assert count == 0
    do_refresh.assert_not_called()


def test_refresh_token_writes_new_expiry(tmp_path):
    start = datetime.now(timezone.utc) + timedelta(minutes=5)
    cache_file = _write(tmp_path, "cache.json", {
        "accessToken": "old-access",
        "refreshToken": "old-refresh",
        "clientId": "cid",
        "clientSecret": "csec",
        "expiresAt": _iso(start),
        "region": "us-east-1",
        "startUrl": "https://example.awsapps.com/start",
    })
    token = json.loads(cache_file.read_text()) | {"_cache_file": str(cache_file)}

    fake_client = SimpleNamespace(
        exceptions=SimpleNamespace(
            InvalidClientException=type("InvalidClientException", (Exception,), {}),
            InvalidGrantException=type("InvalidGrantException", (Exception,), {}),
            UnauthorizedClientException=type("UnauthorizedClientException", (Exception,), {}),
            ExpiredTokenException=type("ExpiredTokenException", (Exception,), {}),
        ),
        create_token=lambda **kwargs: {
            "accessToken": "new-access",
            "expiresIn": 3600,
            "refreshToken": "new-refresh",
        },
    )

    with patch.object(refresh.boto3, "client", return_value=fake_client):
        ok = refresh.refresh_token(token)

    assert ok is True
    written = json.loads(cache_file.read_text())
    assert written["accessToken"] == "new-access"
    assert written["refreshToken"] == "new-refresh"
    assert "_cache_file" not in written
    # expiresAt must parse and be ~1h ahead of now
    remaining = refresh.parse_expiry(written["expiresAt"]) - datetime.now(timezone.utc)
    assert 3500 <= remaining.total_seconds() <= 3700


@pytest.mark.parametrize("exc_name", [
    "InvalidClientException",
    "InvalidGrantException",
    "UnauthorizedClientException",
    "ExpiredTokenException",
])
def test_refresh_token_prompts_on_auth_errors(tmp_path, exc_name):
    cache_file = _write(tmp_path, "cache.json", {
        "accessToken": "a",
        "refreshToken": "r",
        "clientId": "cid",
        "clientSecret": "csec",
        "expiresAt": _iso(datetime.now(timezone.utc) + timedelta(minutes=5)),
        "region": "us-east-1",
        "startUrl": "https://example.awsapps.com/start",
    })
    token = json.loads(cache_file.read_text()) | {"_cache_file": str(cache_file)}

    exceptions = {name: type(name, (Exception,), {}) for name in [
        "InvalidClientException", "InvalidGrantException",
        "UnauthorizedClientException", "ExpiredTokenException",
    ]}

    def raise_it(**kwargs):
        raise exceptions[exc_name]("forced")

    fake_client = SimpleNamespace(
        exceptions=SimpleNamespace(**exceptions),
        create_token=raise_it,
    )

    with patch.object(refresh.boto3, "client", return_value=fake_client), \
         patch.object(refresh, "prompt_sso_login") as prompt:
        ok = refresh.refresh_token(token)

    assert ok is False
    prompt.assert_called_once()


def test_refresh_token_swallows_unexpected_exceptions(tmp_path, caplog):
    cache_file = _write(tmp_path, "cache.json", {
        "accessToken": "a",
        "refreshToken": "r",
        "clientId": "cid",
        "clientSecret": "csec",
        "expiresAt": _iso(datetime.now(timezone.utc) + timedelta(minutes=5)),
        "region": "us-east-1",
        "startUrl": "https://example.awsapps.com/start",
    })
    token = json.loads(cache_file.read_text()) | {"_cache_file": str(cache_file)}

    exceptions = {name: type(name, (Exception,), {}) for name in [
        "InvalidClientException", "InvalidGrantException",
        "UnauthorizedClientException", "ExpiredTokenException",
    ]}

    def explode(**kwargs):
        raise RuntimeError("network is on fire")

    fake_client = SimpleNamespace(
        exceptions=SimpleNamespace(**exceptions),
        create_token=explode,
    )

    with patch.object(refresh.boto3, "client", return_value=fake_client), \
         patch.object(refresh, "prompt_sso_login") as prompt:
        ok = refresh.refresh_token(token)

    assert ok is False
    prompt.assert_not_called()

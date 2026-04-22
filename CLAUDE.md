# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Install for local development:

```bash
pip install -e .
```

Run the CLI directly without installing the entry point:

```bash
python -m aws_sso_keepalive.cli run --once
```

There is no test suite, linter, or formatter configured in this repo.

## Architecture

`aws-sso-keepalive` is a cross-platform Python CLI that keeps AWS SSO sessions alive by refreshing tokens before they expire. The package is laid out under `src/aws_sso_keepalive/` and wired to the `aws-sso-keepalive` entry point in `pyproject.toml`.

The code is split into four modules, each with a narrow responsibility:

- **`cli.py`** — argparse subcommand dispatcher (`run`, `install`, `uninstall`, `status`, `logs`). `run --daemon` on Unix uses a double-fork to detach and writes a PID file to `~/.aws/sso-keepalive.pid`; on Windows it falls through to foreground.
- **`refresh.py`** — discovers tokens in `~/.aws/sso/cache/*.json` and refreshes any expiring within 15 minutes (`REFRESH_BUFFER_MINUTES`). Filters out cache files written by other tools (prefixes `aws-toolkit`, `kiro`) and skips tokens that expired more than 1 hour ago (assumed dead). Refresh uses `boto3.client("sso-oidc").create_token(grantType="refresh_token", ...)` and writes the new `accessToken`/`expiresAt` back to the same cache file, preserving the original JSON shape (keys with a leading `_` are stripped before write).
- **`notify.py`** — only called when the refresh token itself is dead (`UnauthorizedClientException`, `ExpiredTokenException`, `InvalidGrantException`). Dispatches to a platform-specific notification path:
  - macOS: `terminal-notifier` with fallback to `osascript` dialog. The `-execute` script is written to `~/.aws/sso-login.sh` and runs `open <startUrl>` + `aws sso login` — deliberately no terminal app dependency, so it works with Ghostty, iTerm, Kitty, etc.
  - Linux: tries `zenity` then `kdialog`.
  - Windows: PowerShell `MessageBox`.
  - `find_sso_session_for_url` parses `~/.aws/config` to map a `startUrl` back to its `[sso-session <name>]` section so `aws sso login --sso-session <name>` can be invoked.
- **`service.py`** — cross-platform auto-start registration. `install()` first calls `_install_os_deps()` (on macOS offers to download `terminal-notifier` v2.0.0 direct from GitHub into `~/.local/bin/`, avoiding Homebrew), then writes the platform unit file:
  - macOS: launchd plist at `~/Library/LaunchAgents/com.aws.sso-keepalive.plist`, loaded via `launchctl`.
  - Linux: systemd user service + timer at `~/.config/systemd/user/aws-sso-keepalive.{service,timer}`, enabled via `systemctl --user`.
  - Windows: Task Scheduler entry named `AWS SSO Keep-Alive`, created via `schtasks`.

  All three run `aws-sso-keepalive run --once` every 2700 seconds (45 min). The `INTERVAL` constant is duplicated in `cli.py` (`DEFAULT_INTERVAL`) and `service.py` (`INTERVAL`) — keep them in sync.

## Key behavioral invariants

- The tool mutates user cache files at `~/.aws/sso/cache/`. Any change to `refresh.refresh_token` must preserve the JSON structure so the AWS CLI and SDKs continue to read the cache correctly.
- `refresh_all` must never raise on a single failing token — the loop is expected to keep running under a launchd/systemd timer and log errors.
- Platform dispatch is always keyed on `platform.system()` returning `"Darwin"`, `"Linux"`, or `"Windows"`.

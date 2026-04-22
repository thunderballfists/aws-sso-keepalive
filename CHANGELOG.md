# Changelog

## 0.1.1 (2026-04-22)

### Bug Fixes

- Catch `InvalidClientException` from `CreateToken` — previously, expired OIDC
  client registrations (separate ~90-day TTL from the refresh token itself)
  were swallowed by the generic error handler instead of triggering a
  re-authentication prompt.

### Internal

- Deduplicate the 45-minute interval constant; single source of truth in
  `aws_sso_keepalive.DEFAULT_INTERVAL`.
- Add MIT `LICENSE` file, PyPI classifiers, and project URLs in
  `pyproject.toml`.
- Add smoke tests for token filtering, expiry logic, and stale-token skip.

## 0.1.0 (2026-03-23)

Initial release.

### Features

- Headless SSO token refresh via OIDC `refresh_token` grant
- Cross-platform auto-start service (`aws-sso-keepalive install`)
  - macOS: launchd agent
  - Linux: systemd user timer
  - Windows: Task Scheduler
- Native OS notifications when refresh token expires
  - macOS: Notification Center via `terminal-notifier` (with `osascript` fallback)
  - Linux: `zenity` / `kdialog` dialogs
  - Windows: PowerShell MessageBox
- Direct download installer for `terminal-notifier` (~4s, no Homebrew required)
- Stale token detection — skips tokens expired >1 hour to avoid notification spam
- CLI commands: `run`, `install`, `uninstall`, `status`, `logs`

### Bug Fixes

- Use correct boto3 exception names (`UnauthorizedClientException`, `ExpiredTokenException`)
- Notification click runs a shell script instead of hardcoding Terminal.app (works with Ghostty, iTerm, Kitty, etc.)

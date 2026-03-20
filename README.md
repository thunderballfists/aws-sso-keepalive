# aws-sso-keepalive

Keep AWS SSO sessions alive by automatically refreshing tokens before they expire. Fully headless — no browser interaction needed (until the refresh token itself expires).

## Install

```bash
pip install aws-sso-keepalive
# or
pipx install aws-sso-keepalive
```

### Optional: macOS notifications

For native macOS Notification Center alerts when the refresh token expires:

```bash
brew install terminal-notifier
```

On Linux, `zenity` or `kdialog` is used for dialogs (usually pre-installed on GNOME/KDE).

## Usage

```bash
# Refresh tokens once
aws-sso-keepalive run --once

# Run in foreground (refreshes every 45 min)
aws-sso-keepalive run

# Run as background daemon (Unix)
aws-sso-keepalive run --daemon

# Custom interval (30 min)
aws-sso-keepalive run --interval 1800
```

## Auto-start on login

```bash
# Install as a system service (auto-detected per platform)
aws-sso-keepalive install

# Check status
aws-sso-keepalive status

# View logs
aws-sso-keepalive logs
aws-sso-keepalive logs -f    # follow

# Remove the service
aws-sso-keepalive uninstall
```

| Platform | Service type |
|----------|-------------|
| macOS    | launchd agent (`~/Library/LaunchAgents/`) |
| Linux    | systemd user timer (`~/.config/systemd/user/`) |
| Windows  | Task Scheduler |

## How it works

1. Scans `~/.aws/sso/cache/` for tokens with a `refreshToken`
2. If a token expires within 15 minutes, calls the SSO OIDC `CreateToken` API with the `refresh_token` grant
3. Writes the new access token back to the cache file

When the refresh token itself expires (typically 30–90 days), you'll get a native OS notification. On macOS, clicking the notification opens your browser and runs `aws sso login` automatically.

## Requirements

- Python 3.10+
- AWS CLI v2 configured with `sso-session` (provides the refresh token)
- `boto3` (installed as dependency)

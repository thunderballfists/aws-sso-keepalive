# aws-sso-keepalive

Keep AWS SSO sessions alive by automatically refreshing tokens before they expire. Fully headless — no browser interaction needed (until the refresh token itself expires).

Works on **macOS**, **Linux**, and **Windows**.

## Install

```bash
pip install git+https://github.com/thunderballfists/aws-sso-keepalive.git
```

Then set up auto-start:

```bash
aws-sso-keepalive install
```

The installer auto-detects your platform, sets up the background service, and on macOS offers to install `terminal-notifier` for native Notification Center alerts (~4 second direct download from GitHub, no Homebrew needed).

## Usage

```bash
# Refresh tokens once
aws-sso-keepalive run --once

# Run in foreground (checks every 45 min)
aws-sso-keepalive run

# Run as background daemon (Unix)
aws-sso-keepalive run --daemon

# Custom interval (30 min)
aws-sso-keepalive run --interval 1800
```

## Managing the service

```bash
aws-sso-keepalive status      # check if running
aws-sso-keepalive logs        # view log output
aws-sso-keepalive logs -f     # follow logs
aws-sso-keepalive uninstall   # remove the service
```

## Platform support

| Platform | Service type | Notification on token expiry |
|----------|-------------|------------------------------|
| macOS    | launchd agent (`~/Library/LaunchAgents/`) | `terminal-notifier` (Notification Center) or `osascript` dialog |
| Linux    | systemd user timer (`~/.config/systemd/user/`) | `zenity` or `kdialog` dialog |
| Windows  | Task Scheduler | PowerShell MessageBox |

## How it works

1. Checks `~/.aws/sso/cache/` every 45 minutes for tokens with a `refreshToken`
2. If a token expires within 15 minutes, calls the SSO OIDC `CreateToken` API with the `refresh_token` grant
3. Writes the new access token back to the cache file
4. Skips stale tokens that expired more than 1 hour ago

Every tool that uses AWS credentials (CLI, SDK, Terraform, CDK, etc.) benefits — no more mid-work auth interruptions.

When the long-lived refresh token itself expires (~90 days), you get a native OS notification. On macOS, clicking the notification opens your browser to re-authenticate.

## Requirements

- Python 3.10+
- AWS CLI v2 configured with [`sso-session`](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) (provides the refresh token)
- `boto3` (installed as a dependency)

## License

MIT

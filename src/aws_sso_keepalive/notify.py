"""Cross-platform notifications for token expiry."""

import logging
import platform
import subprocess
import webbrowser
from pathlib import Path

log = logging.getLogger("aws-sso-keepalive")


def prompt_sso_login(start_url: str, sso_session: str | None = None):
    if not sso_session:
        sso_session = find_sso_session_for_url(start_url)
    notify_and_login(start_url, sso_session)


def notify_and_login(start_url: str, sso_session: str | None):
    system = platform.system()
    title = "AWS SSO Session Expired"
    message = f"Refresh token expired for {start_url}. Click to re-authenticate."

    login_cmd = "aws sso login"
    if sso_session:
        login_cmd += f" --sso-session {sso_session}"

    try:
        if system == "Darwin":
            _macos_notify(title, message, start_url, login_cmd)
        elif system == "Linux":
            if _linux_dialog(title, message):
                _run_sso_login(start_url, sso_session)
        elif system == "Windows":
            if _windows_dialog(title, message):
                _run_sso_login(start_url, sso_session)
    except Exception as e:
        log.warning("Could not show notification: %s", e)


def _macos_notify(title: str, message: str, start_url: str, login_cmd: str):
    on_click_script = (
        f'open "{start_url}" && '
        f'osascript -e \'tell app "Terminal" to do script "{login_cmd}"\''
    )

    try:
        subprocess.run(
            [
                "terminal-notifier",
                "-title", title,
                "-subtitle", "Click to re-authenticate",
                "-message", message,
                "-execute", on_click_script,
                "-timeout", "120",
                "-sound", "default",
                "-ignoreDnD",
            ],
            check=False,
        )
        log.info("Notification sent — click it to open browser and run `%s`.", login_cmd)
        return
    except FileNotFoundError:
        pass

    # Fallback: osascript modal dialog
    escaped_msg = message.replace('"', '\\"')
    result = subprocess.run(
        [
            "osascript", "-e",
            f'display alert "{title}" message "{escaped_msg}" '
            f'buttons {{"Dismiss", "Login Now"}} default button "Login Now" '
            f'giving up after 120',
        ],
        capture_output=True, text=True, check=False,
    )
    if "Login Now" in result.stdout:
        _run_sso_login(start_url, None)


def _linux_dialog(title: str, message: str) -> bool:
    for cmd in [
        ["zenity", "--question", "--title", title, "--text", message,
         "--ok-label", "Login Now", "--cancel-label", "Dismiss", "--width", "400"],
        ["kdialog", "--yesno", message, "--title", title,
         "--yes-label", "Login Now", "--no-label", "Dismiss"],
    ]:
        try:
            result = subprocess.run(cmd, check=False)
            return result.returncode == 0
        except FileNotFoundError:
            continue
    return False


def _windows_dialog(title: str, message: str) -> bool:
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"$r = [System.Windows.Forms.MessageBox]::Show("
        f"'{message}', '{title}', 'YesNo', 'Warning'); "
        f"if ($r -eq 'Yes') {{ exit 0 }} else {{ exit 1 }}"
    )
    result = subprocess.run(["powershell", "-Command", ps_script], check=False)
    return result.returncode == 0


def _run_sso_login(start_url: str, sso_session: str | None):
    cmd = ["aws", "sso", "login"]
    if sso_session:
        cmd += ["--sso-session", sso_session]
    webbrowser.open(start_url)
    subprocess.run(cmd, check=False)


def find_sso_session_for_url(start_url: str) -> str | None:
    config_file = Path.home() / ".aws" / "config"
    if not config_file.exists():
        return None
    try:
        content = config_file.read_text()
    except OSError:
        return None

    current_session = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[sso-session "):
            current_session = line.split("]")[0].replace("[sso-session ", "")
        elif line.startswith("sso_start_url") and current_session:
            url = line.split("=", 1)[1].strip()
            if url == start_url:
                return current_session
    return None

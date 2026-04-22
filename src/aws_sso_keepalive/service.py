"""Cross-platform service install/uninstall for auto-start on login."""

import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from . import DEFAULT_INTERVAL as INTERVAL

LABEL = "com.aws.sso-keepalive"


def get_exe_path() -> str:
    """Get the path to the installed aws-sso-keepalive entry point."""
    return shutil.which("aws-sso-keepalive") or sys.executable


def install():
    system = platform.system()
    _install_os_deps(system)
    if system == "Darwin":
        _install_launchd()
    elif system == "Linux":
        _install_systemd()
    elif system == "Windows":
        _install_task_scheduler()
    else:
        print(f"Unsupported platform: {system}")
        sys.exit(1)


def uninstall():
    system = platform.system()
    if system == "Darwin":
        _uninstall_launchd()
    elif system == "Linux":
        _uninstall_systemd()
    elif system == "Windows":
        _uninstall_task_scheduler()
    else:
        print(f"Unsupported platform: {system}")
        sys.exit(1)


# --- OS-level dependencies ---

_TN_VERSION = "2.0.0"
_TN_GITHUB_URL = (
    f"https://github.com/julienXX/terminal-notifier/releases/download/{_TN_VERSION}"
    f"/terminal-notifier-{_TN_VERSION}.zip"
)
_TN_APP_INSTALL_DIR = Path.home() / ".local" / "bin"


def _install_os_deps(system: str):
    if system == "Darwin":
        _install_terminal_notifier()
    elif system == "Linux":
        if not (shutil.which("zenity") or shutil.which("kdialog")):
            print("\n  zenity/kdialog (optional): not found")
            print("    Needed for desktop dialogs when refresh token expires.")
            print("    Install: sudo apt install zenity  (or your distro equivalent)")


def _install_terminal_notifier():
    if shutil.which("terminal-notifier"):
        print("  terminal-notifier: already installed")
        return

    print("\nterminal-notifier enables native macOS notifications.")
    print("Install methods:")
    print("  1) Direct download from GitHub (~4s, recommended)")
    print("  2) Homebrew:   brew install terminal-notifier")
    print("  3) Skip (falls back to osascript dialog)")

    choice = input("\nChoice [1/2/3]: ").strip()

    if choice == "1":
        _install_tn_direct()
    elif choice == "2":
        if not shutil.which("brew"):
            print("  Homebrew not found. Try option 1 instead.")
            return
        subprocess.run(["brew", "install", "terminal-notifier"], check=False)
    elif choice == "3":
        print("  Skipped. Will use osascript dialog as fallback.")
        return
    else:
        print("  Skipped.")
        return

    if shutil.which("terminal-notifier"):
        print("  terminal-notifier: installed")
    else:
        print("  terminal-notifier: not found on PATH after install.")
        print("  Notifications will fall back to osascript dialog.")


def _install_tn_direct():
    """Download terminal-notifier.app from GitHub and install to ~/.local/bin/."""
    import io
    import urllib.request
    import zipfile

    print(f"  Downloading from GitHub ({_TN_VERSION})...")
    try:
        resp = urllib.request.urlopen(_TN_GITHUB_URL, timeout=30)
        data = resp.read()
    except Exception as e:
        print(f"  Download failed: {e}")
        return

    _TN_APP_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Extract only the .app bundle (skip README, etc.)
        for member in zf.namelist():
            if not member.startswith("terminal-notifier.app"):
                continue
            target = _TN_APP_INSTALL_DIR / member
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))

    app_dir = _TN_APP_INSTALL_DIR / "terminal-notifier.app"

    # Create a symlink to the binary
    tn_binary = app_dir / "Contents" / "MacOS" / "terminal-notifier"
    tn_link = _TN_APP_INSTALL_DIR / "terminal-notifier"

    if tn_binary.exists():
        tn_binary.chmod(0o755)
        tn_link.unlink(missing_ok=True)
        tn_link.symlink_to(tn_binary)
        print(f"  Installed to {tn_link}")
        # Check if ~/.local/bin is on PATH
        if str(_TN_APP_INSTALL_DIR) not in os.environ.get("PATH", ""):
            print(f"\n  NOTE: Add {_TN_APP_INSTALL_DIR} to your PATH:")
            print(f'    echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.zshrc')
    else:
        print(f"  Error: binary not found at {tn_binary}")


# --- macOS (launchd) ---

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _install_launchd():
    exe = get_exe_path()
    log_file = Path.home() / ".aws" / "sso-keepalive.log"
    plist_path = _launchd_plist_path()

    plist = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{LABEL}</string>
            <key>ProgramArguments</key>
            <array>
                <string>{exe}</string>
                <string>run</string>
                <string>--once</string>
            </array>
            <key>StartInterval</key>
            <integer>{INTERVAL}</integer>
            <key>RunAtLoad</key>
            <true/>
            <key>StandardOutPath</key>
            <string>{log_file}</string>
            <key>StandardErrorPath</key>
            <string>{log_file}</string>
        </dict>
        </plist>
    """)

    # Unload existing if present
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False,
                        capture_output=True)

    plist_path.write_text(plist)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(f"Installed and started launchd agent.")
    print(f"  Plist:    {plist_path}")
    print(f"  Log:      {log_file}")
    print(f"  Interval: every {INTERVAL}s ({INTERVAL // 60} min)")


def _uninstall_launchd():
    plist_path = _launchd_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        print("Uninstalled launchd agent.")
    else:
        print("Launchd agent not installed.")


# --- Linux (systemd user service) ---

def _systemd_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _install_systemd():
    exe = get_exe_path()
    unit_dir = _systemd_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)

    service_file = unit_dir / "aws-sso-keepalive.service"
    service_file.write_text(textwrap.dedent(f"""\
        [Unit]
        Description=AWS SSO Keep-Alive

        [Service]
        Type=oneshot
        ExecStart={exe} run --once

        [Install]
        WantedBy=default.target
    """))

    timer_file = unit_dir / "aws-sso-keepalive.timer"
    timer_file.write_text(textwrap.dedent(f"""\
        [Unit]
        Description=AWS SSO Keep-Alive Timer

        [Timer]
        OnBootSec=60
        OnUnitActiveSec={INTERVAL}
        Persistent=true

        [Install]
        WantedBy=timers.target
    """))

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "aws-sso-keepalive.timer"], check=True)
    print("Installed and started systemd user timer.")
    print(f"  Service: {service_file}")
    print(f"  Timer:   {timer_file}")
    print(f"  Interval: every {INTERVAL}s ({INTERVAL // 60} min)")
    print()
    print("Check status: systemctl --user status aws-sso-keepalive.timer")


def _uninstall_systemd():
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "aws-sso-keepalive.timer"],
        check=False,
    )
    unit_dir = _systemd_dir()
    for name in ["aws-sso-keepalive.service", "aws-sso-keepalive.timer"]:
        f = unit_dir / name
        if f.exists():
            f.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print("Uninstalled systemd user timer.")


# --- Windows (Task Scheduler) ---

TASK_NAME = "AWS SSO Keep-Alive"


def _install_task_scheduler():
    exe = get_exe_path()
    # schtasks requires the full command as a single string
    action = f'"{sys.executable}" -m aws_sso_keepalive run --once'

    subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", TASK_NAME,
            "/TR", action,
            "/SC", "MINUTE",
            "/MO", str(INTERVAL // 60),
            "/F",  # force overwrite
        ],
        check=True,
    )
    print(f"Installed Windows scheduled task: {TASK_NAME}")
    print(f"  Interval: every {INTERVAL // 60} min")
    print()
    print(f"Check status: schtasks /Query /TN \"{TASK_NAME}\"")


def _uninstall_task_scheduler():
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Uninstalled Windows scheduled task: {TASK_NAME}")
    else:
        print("Task not found or already removed.")


# --- Status ---

def status():
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["launchctl", "list", LABEL],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            print("Status: running")
            print(result.stdout)
        else:
            print("Status: not installed")

    elif system == "Linux":
        subprocess.run(
            ["systemctl", "--user", "status", "aws-sso-keepalive.timer"],
            check=False,
        )

    elif system == "Windows":
        subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
            check=False,
        )

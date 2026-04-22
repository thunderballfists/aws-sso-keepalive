"""CLI entry point for aws-sso-keepalive."""

import argparse
import logging
import os
import platform
import signal
import sys
import time
from pathlib import Path

from . import DEFAULT_INTERVAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aws-sso-keepalive")


def cmd_run(args):
    from .refresh import refresh_all

    if args.once:
        refresh_all()
        return

    if args.daemon:
        _daemonize()

    running = True

    def handle_signal(signum, frame):
        nonlocal running
        log.info("Received signal %d, shutting down...", signum)
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log.info("Starting keep-alive loop (interval: %ds)", args.interval)

    while running:
        try:
            refresh_all()
        except Exception as e:
            log.error("Unexpected error: %s", e)

        for _ in range(args.interval):
            if not running:
                break
            time.sleep(1)

    log.info("Keep-alive stopped.")
    pid_file = Path.home() / ".aws" / "sso-keepalive.pid"
    pid_file.unlink(missing_ok=True)


def cmd_install(args):
    from .service import install
    install()


def cmd_uninstall(args):
    from .service import uninstall
    uninstall()


def cmd_status(args):
    from .service import status
    status()


def cmd_logs(args):
    log_file = Path.home() / ".aws" / "sso-keepalive.log"
    if not log_file.exists():
        print("No log file found.")
        return
    if args.follow:
        os.execlp("tail", "tail", "-f", str(log_file))
    else:
        print(log_file.read_text())


def _daemonize():
    if platform.system() == "Windows":
        log.info("Windows detected — running in foreground.")
        return

    pid = os.fork()
    if pid > 0:
        print(f"Daemon started with PID {pid}")
        sys.exit(0)

    os.setsid()

    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    sys.stdin = open(os.devnull, "r")
    log_file = Path.home() / ".aws" / "sso-keepalive.log"
    log_handler = logging.FileHandler(str(log_file))
    log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.handlers = [log_handler]
    log.info("Daemon started, logging to %s", log_file)

    pid_file = Path.home() / ".aws" / "sso-keepalive.pid"
    pid_file.write_text(str(os.getpid()))


def main():
    parser = argparse.ArgumentParser(
        prog="aws-sso-keepalive",
        description="Keep AWS SSO sessions alive by refreshing tokens before they expire",
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Run the token refresh loop")
    p_run.add_argument("--once", action="store_true", help="Refresh once and exit")
    p_run.add_argument("--daemon", action="store_true", help="Daemonize (Unix only)")
    p_run.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Check interval in seconds (default: {DEFAULT_INTERVAL})")
    p_run.set_defaults(func=cmd_run)

    # install
    p_install = sub.add_parser("install", help="Install as auto-start service")
    p_install.set_defaults(func=cmd_install)

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Remove auto-start service")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # status
    p_status = sub.add_parser("status", help="Show service status")
    p_status.set_defaults(func=cmd_status)

    # logs
    p_logs = sub.add_parser("logs", help="Show log output")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)

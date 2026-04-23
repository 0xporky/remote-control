#!/usr/bin/env python3.11
"""CLI entrypoint for the remote-control deploy pipeline.

Usage:
    python deploy/deploy.py up
    python deploy/deploy.py down [--clear-dns]

The same code paths are importable from `rc_deploy` for the Telegram bot.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as `python deploy/deploy.py …` without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rc_deploy import (  # noqa: E402
    DeployConfig,
    ProgressEvent,
    deploy_down,
    deploy_up,
    load_config,
)
from rc_deploy.config import ConfigError  # noqa: E402

CYAN = "\033[1;36m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
RESET = "\033[0m"

_COLOR = {"info": CYAN, "warn": YELLOW, "error": RED}


def _print(cmd: str, evt: ProgressEvent) -> None:
    color = _COLOR.get(evt.level, CYAN)
    print(f"{color}[{cmd}]{RESET} [{evt.stage}] {evt.message}", flush=True)


async def _run_up(config: DeployConfig) -> int:
    had_error = False
    async for evt in deploy_up(config):
        _print("up", evt)
        if evt.level == "error":
            had_error = True
    return 1 if had_error else 0


async def _run_down(config: DeployConfig, clear_dns: bool) -> int:
    had_error = False
    async for evt in deploy_down(config, clear_dns=clear_dns):
        _print("down", evt)
        if evt.level == "error":
            had_error = True
    return 1 if had_error else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Provision and tear down the remote-control stack on DigitalOcean.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("up", help="Provision droplet, deploy server + web, configure DNS and TLS.")

    down_cmd = sub.add_parser(
        "down",
        help="Destroy the droplet tracked in deploy/.state.json.",
    )
    down_cmd.add_argument(
        "--clear-dns",
        action="store_true",
        help="Also delete the A-record from DigitalOcean DNS.",
    )

    args = parser.parse_args()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"{RED}[config]{RESET} {exc}", file=sys.stderr)
        sys.exit(2)

    if args.cmd == "up":
        rc = asyncio.run(_run_up(config))
    else:
        rc = asyncio.run(_run_down(config, clear_dns=args.clear_dns))
    sys.exit(rc)


if __name__ == "__main__":
    main()

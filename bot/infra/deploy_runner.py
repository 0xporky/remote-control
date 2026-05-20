"""Bridge between Telegram handlers and the rc_deploy async generators.

Builds a DeployConfig with bot-generated overrides for SUBDOMAIN/SECRET_KEY/
AGENT_TOKENS/TURN_SECRET, then streams ProgressEvent objects to the caller
via a callback. Keeps no global state — handlers own the message editor.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Awaitable, Callable

# Allow `import rc_deploy` even when the bot runs without installing the deploy package.
# bot/infra/deploy_runner.py → repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "deploy"))

from rc_deploy import (  # noqa: E402
    DeployConfig,
    ProgressEvent,
    deploy_down,
    deploy_up,
    load_config,
)

from state import Secrets  # noqa: E402

ProgressCallback = Callable[[ProgressEvent], Awaitable[None]]


def build_config(subdomain: str, secrets: Secrets) -> DeployConfig:
    """Load static vars from deploy/.env and splice in the four dynamic ones."""
    return load_config(
        overrides={
            "SUBDOMAIN": subdomain,
            "SECRET_KEY": secrets.secret_key,
            "AGENT_TOKENS": secrets.agent_tokens,
            "TURN_SECRET": secrets.turn_secret,
        }
    )


async def run_up(config: DeployConfig, on_event: ProgressCallback) -> bool:
    """Drive deploy_up, forwarding every event. Returns True if no error-level event was seen."""
    had_error = False
    async for evt in deploy_up(config):
        if evt.level == "error":
            had_error = True
        await on_event(evt)
    return not had_error


async def run_down(config: DeployConfig, on_event: ProgressCallback) -> bool:
    had_error = False
    async for evt in deploy_down(config, clear_dns=True):
        if evt.level == "error":
            had_error = True
        await on_event(evt)
    return not had_error

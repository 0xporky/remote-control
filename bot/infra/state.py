"""Infra-bot state persisted between /up and /down (survives bot restarts).

Lives at bot/infra/.state.json. Holds the dynamic deploy values generated for
the current up→down cycle so a teardown still has the right SUBDOMAIN/secrets
even if the bot process restarted in between. Cleared at the end of /down.

Differs from the Agent bot's state by carrying the full Secrets triple (needed
to rebuild DeployConfig for /down) and not carrying any agent_pid (this bot
never spawns the agent — see bot/agent/).
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

STATE_PATH = (Path(__file__).resolve().parent / ".state.json").resolve()

Status = Literal["deploying", "up", "tearing_down"]


@dataclass(frozen=True)
class Secrets:
    secret_key: str
    agent_tokens: str
    turn_secret: str


@dataclass(frozen=True)
class BotState:
    status: Status
    subdomain: str
    fqdn: str
    secrets: Secrets
    started_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


def read_state(path: Path = STATE_PATH) -> BotState | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    s = data.get("secrets") or {}
    return BotState(
        status=data["status"],
        subdomain=data["subdomain"],
        fqdn=data["fqdn"],
        secrets=Secrets(
            secret_key=s.get("secret_key", ""),
            agent_tokens=s.get("agent_tokens", ""),
            turn_secret=s.get("turn_secret", ""),
        ),
        started_at=data.get("started_at", ""),
    )


def write_state(state: BotState, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def clear_state(path: Path = STATE_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass

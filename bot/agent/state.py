"""Agent-bot state persisted between /up and /down (survives bot restarts).

Lives at bot/agent/.state.json. Holds just enough to terminate the agent
subprocess after a bot restart — the agent PID, the FQDN/subdomain that the
agent is connected to, and a status tag.

Crucially does NOT persist the secrets (AGENT_TOKENS, TURN_SECRET). Those are
runtime-only: the user re-pastes the credentials blob from the Infra bot if a
new /up cycle is needed. This limits how long live secrets live on the
Windows host's disk.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

STATE_PATH = (Path(__file__).resolve().parent / ".state.json").resolve()

Status = Literal["starting", "up", "stopping"]


@dataclass(frozen=True)
class BotState:
    status: Status
    subdomain: str
    fqdn: str
    agent_pid: int | None = None
    started_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


def read_state(path: Path = STATE_PATH) -> BotState | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return BotState(
        status=data["status"],
        subdomain=data["subdomain"],
        fqdn=data["fqdn"],
        agent_pid=data.get("agent_pid"),
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

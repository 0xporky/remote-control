from dataclasses import dataclass
from typing import Literal

Stage = Literal[
    "preflight",
    "droplet",
    "dns",
    "ssh",
    "cloudinit",
    "rsync",
    "env",
    "compose",
    "health",
    "done",
]
Level = Literal["info", "warn", "error"]


@dataclass(frozen=True)
class ProgressEvent:
    stage: Stage
    message: str
    level: Level = "info"
    droplet_id: str | None = None
    ip: str | None = None
    fqdn: str | None = None

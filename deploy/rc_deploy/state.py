import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_PATH = (Path(__file__).resolve().parent.parent / ".state.json").resolve()


@dataclass(frozen=True)
class State:
    droplet_id: str
    ip: str
    name: str
    fqdn: str


def read_state(path: Path = STATE_PATH) -> State | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    return State(
        droplet_id=str(data.get("droplet_id") or ""),
        ip=str(data.get("ip") or ""),
        name=str(data.get("name") or ""),
        fqdn=str(data.get("fqdn") or ""),
    )


def write_state(state: State, path: Path = STATE_PATH) -> None:
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

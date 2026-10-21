import asyncio
import base64
import os
import shlex
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable

import httpx


def _rsync_path(p: Path | str) -> str:
    """Convert a path to a form rsync understands.

    On Windows, MSYS2/Cygwin rsync interprets `C:\\...` as a remote target
    (colon = host separator), so we rewrite drive letters into MSYS form:
    `C:\\Users\\foo` -> `/c/Users/foo`.
    """
    s = str(p)
    if sys.platform != "win32":
        return s
    if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        tail = s[2:].lstrip("\\/").replace("\\", "/")
        return f"/{drive}/{tail}"
    return s.replace("\\", "/")

SSH_OPTS: list[str] = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "ConnectTimeout=5",
    # Every call here is unattended (the bot runs without a tty), and
    # wait_for_ssh retries 60 times. Without BatchMode a passphrase-protected
    # key makes ssh reach for /dev/tty on every single attempt, which only
    # surfaces as "Permission denied (publickey)" two minutes later.
    "-o", "BatchMode=yes",
]


@dataclass(frozen=True)
class SSHResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class HealthAttempt:
    attempt: int
    elapsed: float
    ok: bool
    error: str | None


class SSHError(RuntimeError):
    def __init__(self, cmd: list[str], result: SSHResult):
        self.cmd = cmd
        self.result = result
        super().__init__(
            f"Command failed (rc={result.returncode}): {' '.join(shlex.quote(c) for c in cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )


_OPENSSH_MAGIC = b"openssh-key-v1\x00"


def key_cipher(key: Path) -> str | None:
    """Cipher protecting an OpenSSH private key — `"none"` when it has no passphrase.

    The cipher name sits in clear text at the head of the base64 blob, before
    anything that the passphrase actually protects, so this needs no secrets.
    Returns None when the file is not in the OpenSSH container format (legacy
    PEM, PuTTY, ...) — there we can't tell and don't guess.
    """
    try:
        text = key.read_text(errors="replace")
    except OSError:
        return None
    if "OPENSSH PRIVATE KEY" not in text:
        return None
    body = "".join(ln for ln in text.splitlines() if not ln.startswith("-----"))
    try:
        blob = base64.b64decode(body)
    except (ValueError, TypeError):
        return None
    if not blob.startswith(_OPENSSH_MAGIC) or len(blob) < len(_OPENSSH_MAGIC) + 4:
        return None
    rest = blob[len(_OPENSSH_MAGIC):]
    (length,) = struct.unpack(">I", rest[:4])
    return rest[4:4 + length].decode("ascii", errors="replace")


async def ssh_agent_available() -> bool:
    """True when an ssh-agent holding at least one identity is reachable.

    An agent can unlock a passphrase-protected key on our behalf, so its
    presence is what makes such a key usable without a tty.
    """
    if not os.environ.get("SSH_AUTH_SOCK"):
        return False
    try:
        result = await _run(["ssh-add", "-l"], timeout=5.0)
    except (asyncio.TimeoutError, OSError):
        return False
    return result.returncode == 0


def _ssh_base(key: Path) -> list[str]:
    return ["ssh", "-i", str(key), *SSH_OPTS]


async def _run(cmd: list[str], *, timeout: float | None = None) -> SSHResult:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return SSHResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
    )


async def ssh_exec(
    ip: str,
    key: Path,
    command: str,
    *,
    timeout: float | None = None,
    check: bool = True,
) -> SSHResult:
    cmd = [*_ssh_base(key), f"rc@{ip}", command]
    result = await _run(cmd, timeout=timeout)
    if check and result.returncode != 0:
        raise SSHError(cmd, result)
    return result


async def scp(src: Path, dst: str, key: Path, *, timeout: float | None = None) -> None:
    cmd = ["scp", "-i", str(key), *SSH_OPTS, "-q", str(src), dst]
    result = await _run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise SSHError(cmd, result)


def _rsync_ssh_arg(key: Path) -> str:
    parts = ["ssh", "-i", shlex.quote(_rsync_path(key))] + [shlex.quote(o) for o in SSH_OPTS]
    return " ".join(parts)


async def rsync(
    src: Path,
    dst: str,
    key: Path,
    *,
    delete: bool = False,
    excludes: Iterable[str] = (),
    timeout: float | None = None,
) -> None:
    cmd: list[str] = ["rsync", "-a"]
    if delete:
        cmd.append("--delete")
    cmd += ["-e", _rsync_ssh_arg(key)]
    for pattern in excludes:
        cmd += ["--exclude", pattern]
    # Append trailing slash on directories so rsync copies *contents* into dst
    # (Path() strips trailing slashes from the call site, so we re-add it here).
    src_str = _rsync_path(src)
    if src.is_dir():
        src_str += "/"
    cmd += [src_str, dst]
    result = await _run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise SSHError(cmd, result)


async def rsync_files(
    files: list[Path],
    dst: str,
    key: Path,
    *,
    timeout: float | None = None,
) -> None:
    cmd: list[str] = ["rsync", "-a", "-e", _rsync_ssh_arg(key)]
    cmd += [_rsync_path(f) for f in files]
    cmd.append(dst)
    result = await _run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise SSHError(cmd, result)


async def wait_for_ssh(
    ip: str, key: Path, *, tries: int = 60, delay: float = 2.0
) -> None:
    last_error = ""
    for _ in range(tries):
        result = await ssh_exec(ip, key, "true", check=False)
        if result.returncode == 0:
            return
        # A booting droplet refuses the connection; a key problem answers
        # instantly with a real message. Keep it so the timeout can say which.
        stderr_lines = result.stderr.strip().splitlines()
        last_error = stderr_lines[-1] if stderr_lines else ""
        await asyncio.sleep(delay)
    msg = f"Timed out waiting for SSH on {ip} after {tries * delay:.0f}s"
    if last_error:
        msg += f" (last error: {last_error})"
    raise TimeoutError(msg)


async def wait_for_cloud_init(
    ip: str, key: Path, *, tries: int = 120, delay: float = 3.0
) -> None:
    probe = (
        "test -f /var/lib/cloud/instance/cloud-init-complete "
        "&& command -v docker >/dev/null"
    )
    for _ in range(tries):
        result = await ssh_exec(ip, key, probe, check=False)
        if result.returncode == 0:
            return
        await asyncio.sleep(delay)
    raise TimeoutError(
        f"Timed out waiting for cloud-init on {ip} after {tries * delay:.0f}s"
    )


async def wait_for_health(
    url: str,
    *,
    tries: int = 10,
    delay: float = 30.0,
    request_timeout: float = 10.0,
) -> AsyncIterator[HealthAttempt]:
    loop = asyncio.get_event_loop()
    start = loop.time()
    async with httpx.AsyncClient(follow_redirects=True, timeout=request_timeout) as client:
        for attempt in range(1, tries + 1):
            error: str | None = None
            ok = False
            try:
                resp = await client.get(url)
                if resp.status_code < 400:
                    ok = True
                else:
                    error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:
                error = type(exc).__name__
            yield HealthAttempt(
                attempt=attempt,
                elapsed=loop.time() - start,
                ok=ok,
                error=error,
            )
            if ok:
                return
            if attempt < tries:
                await asyncio.sleep(delay)

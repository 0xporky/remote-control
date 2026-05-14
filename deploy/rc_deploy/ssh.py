import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable

import httpx

SSH_OPTS: list[str] = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
    "-o", "ConnectTimeout=5",
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
    parts = ["ssh", "-i", shlex.quote(str(key))] + [shlex.quote(o) for o in SSH_OPTS]
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
    src_str = f"{src}/" if src.is_dir() else str(src)
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
    cmd += [str(f) for f in files]
    cmd.append(dst)
    result = await _run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise SSHError(cmd, result)


async def wait_for_ssh(
    ip: str, key: Path, *, tries: int = 60, delay: float = 2.0
) -> None:
    for _ in range(tries):
        result = await ssh_exec(ip, key, "true", check=False)
        if result.returncode == 0:
            return
        await asyncio.sleep(delay)
    raise TimeoutError(f"Timed out waiting for SSH on {ip} after {tries * delay:.0f}s")


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

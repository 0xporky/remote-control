"""Spawn and stop the local agent subprocess.

start() spawns `python agent/main.py …`, drains its stdout, and resolves to
StartResult once the readiness line is seen, the process exits, or the timeout
elapses. stop() terminates either an in-memory Process handle or, after a bot
restart, the PID recovered from bot/agent/.state.json (using psutil).

Readiness signal: `agent/signaling.py:83` logs "Registered as agent: <id>"
right after the WebSocket register handshake — the canonical "agent is up"
moment.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

# bot/agent/agent_runner.py → repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENT_DIR = _REPO_ROOT / "agent"
_AGENT_ENTRY = _AGENT_DIR / "main.py"

_READY_RE = re.compile(r"Registered as agent", re.IGNORECASE)
_READY_TIMEOUT_SECONDS = 30.0
_TERMINATE_GRACE_SECONDS = 5.0
_RECENT_LINES_KEPT = 30


@dataclass
class StartResult:
    ok: bool
    pid: int | None
    error: str | None = None
    tail: str = ""  # last few lines of agent stdout — surfaced to chat on failure


class AgentRunner:
    """Owns the running agent subprocess. One per bot process."""

    def __init__(self, python_bin: str):
        self.python_bin = python_bin
        self._proc: asyncio.subprocess.Process | None = None
        self._drain_task: asyncio.Task | None = None
        self._recent: deque[str] = deque(maxlen=_RECENT_LINES_KEPT)

    async def start(
        self,
        *,
        fqdn: str,
        agent_token: str,
        turn_secret: str,
    ) -> StartResult:
        if self._proc and self._proc.returncode is None:
            return StartResult(ok=False, pid=self._proc.pid, error="Agent is already running")

        turn_urls = f"turn:{fqdn}:3478?transport=udp,turn:{fqdn}:3478?transport=tcp"
        args = [
            self.python_bin,
            str(_AGENT_ENTRY),
            f"--server=wss://{fqdn}/ws/signaling",
            f"--token={agent_token}",
            f"--turn-urls={turn_urls}",
            f"--turn-secret={turn_secret}",
        ]
        logger.info("Spawning agent: %s", " ".join(a if "--token" not in a and "--turn-secret" not in a else a.split("=")[0] + "=***" for a in args))

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(_AGENT_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            return StartResult(ok=False, pid=None, error=f"Failed to spawn agent: {exc}")

        ready_event = asyncio.Event()
        self._recent.clear()
        self._drain_task = asyncio.create_task(self._drain_stdout(ready_event))

        # Wait for one of: ready line, process exit, timeout.
        exit_waiter = asyncio.create_task(self._proc.wait())
        ready_waiter = asyncio.create_task(ready_event.wait())
        done, pending = await asyncio.wait(
            {exit_waiter, ready_waiter},
            timeout=_READY_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        if ready_waiter in done:
            return StartResult(ok=True, pid=self._proc.pid)

        if exit_waiter in done:
            tail = "\n".join(self._recent)
            await self._cleanup_drain()
            rc = self._proc.returncode
            self._proc = None
            return StartResult(
                ok=False,
                pid=None,
                error=f"Agent exited with code {rc} before becoming ready",
                tail=tail,
            )

        # Timeout.
        tail = "\n".join(self._recent)
        await self._terminate_proc(self._proc)
        await self._cleanup_drain()
        pid = self._proc.pid
        self._proc = None
        return StartResult(
            ok=False,
            pid=pid,
            error=f"Agent did not register within {int(_READY_TIMEOUT_SECONDS)}s; killed",
            tail=tail,
        )

    async def stop(self, pid_from_state: int | None = None) -> None:
        """Terminate the in-memory agent if any, else fall back to PID from state."""
        if self._proc and self._proc.returncode is None:
            await self._terminate_proc(self._proc)
        elif pid_from_state is not None:
            await asyncio.to_thread(_terminate_pid, pid_from_state)
        await self._cleanup_drain()
        self._proc = None

    async def _drain_stdout(self, ready_event: asyncio.Event) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                line_bytes = await self._proc.stdout.readline()
                if not line_bytes:
                    return
                line = line_bytes.decode(errors="replace").rstrip()
                self._recent.append(line)
                if not ready_event.is_set() and _READY_RE.search(line):
                    ready_event.set()
        except asyncio.CancelledError:
            return

    async def _cleanup_drain(self) -> None:
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except (asyncio.CancelledError, Exception):
                pass
        self._drain_task = None

    async def _terminate_proc(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE_SECONDS)
            except asyncio.TimeoutError:
                logger.warning("Agent pid=%s did not exit after kill()", proc.pid)


def _terminate_pid(pid: int) -> None:
    """Sync helper used via to_thread to terminate a PID recovered from state."""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=_TERMINATE_GRACE_SECONDS)
            return
        except psutil.TimeoutExpired:
            pass
        proc.kill()
        try:
            proc.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except psutil.TimeoutExpired:
            logger.warning("PID %s did not exit after kill()", pid)
    except psutil.NoSuchProcess:
        return

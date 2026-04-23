import asyncio
from typing import AsyncIterator

from .config import DeployConfig
from .do_client import DOClient
from .progress import ProgressEvent
from .ssh import SSHError, ssh_exec
from .state import clear_state, read_state


async def deploy_down(
    config: DeployConfig, *, clear_dns: bool = False
) -> AsyncIterator[ProgressEvent]:
    state = read_state()
    if state is None:
        yield ProgressEvent(
            "preflight",
            "No .state.json — nothing to destroy.",
            level="warn",
        )
        return

    yield ProgressEvent(
        "preflight",
        f"Tearing down droplet={state.droplet_id} ip={state.ip} fqdn={state.fqdn}",
        droplet_id=state.droplet_id,
        ip=state.ip,
        fqdn=state.fqdn,
    )

    do = DOClient(config.do_api_token)

    # Best-effort graceful container shutdown.
    if state.ip and config.ssh_private_key.is_file():
        yield ProgressEvent(
            "compose",
            "Attempting graceful docker compose down (10s timeout)...",
            ip=state.ip,
        )
        try:
            await ssh_exec(
                state.ip,
                config.ssh_private_key,
                "cd app && docker compose down",
                timeout=10.0,
            )
        except (asyncio.TimeoutError, SSHError) as exc:
            yield ProgressEvent(
                "compose",
                f"Graceful shutdown skipped or failed — proceeding anyway ({type(exc).__name__}).",
                level="warn",
            )
    else:
        yield ProgressEvent(
            "compose",
            "Skipping graceful shutdown (missing IP or SSH key).",
            level="warn",
        )

    # Destroy droplet.
    yield ProgressEvent(
        "droplet",
        f"Deleting droplet {state.droplet_id}...",
        droplet_id=state.droplet_id,
    )
    await do.delete_droplet(state.droplet_id)

    # Optional DNS cleanup.
    if clear_dns:
        yield ProgressEvent(
            "dns",
            f"Deleting A-record {config.fqdn}...",
            fqdn=config.fqdn,
        )
        deleted = await do.delete_a_record(config.domain, config.subdomain)
        yield ProgressEvent(
            "dns",
            "A-record deleted." if deleted else "No A-record found to delete.",
            level="info" if deleted else "warn",
            fqdn=config.fqdn,
        )

    clear_state()
    yield ProgressEvent(
        "done",
        "Teardown complete. Compute billing has stopped.",
    )

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from .config import DeployConfig
from .do_client import DOClient
from .progress import ProgressEvent
from .ssh import (
    rsync,
    rsync_files,
    scp,
    ssh_exec,
    wait_for_cloud_init,
    wait_for_health,
    wait_for_ssh,
)
from .state import State, read_state, write_state

SERVER_EXCLUDES = ("node_modules", "dist", "__pycache__", ".venv", "venv")
WEB_EXCLUDES = ("node_modules", "dist", "__pycache__")


def _render_remote_env(config: DeployConfig) -> str:
    lines = [
        f"FQDN={config.fqdn}",
        f"SECRET_KEY={config.secret_key}",
        f"AUTH_PASSWORD={config.auth_password}",
        f"AGENT_TOKEN_REQUIRED={'true' if config.agent_token_required else 'false'}",
        f"AGENT_TOKENS={config.agent_tokens}",
        f"GOOGLE_CLIENT_ID={config.google_client_id}",
        f"GOOGLE_ALLOWED_EMAILS={config.google_allowed_emails}",
        f"GOOGLE_ALLOWED_DOMAINS={config.google_allowed_domains}",
        f"ACCESS_TOKEN_EXPIRE_MINUTES={config.access_token_expire_minutes}",
        f"WS_SESSION_TIMEOUT_SECONDS={config.ws_session_timeout_seconds}",
    ]
    return "\n".join(lines) + "\n"


async def deploy_up(config: DeployConfig) -> AsyncIterator[ProgressEvent]:
    # ── 1. preflight ─────────────────────────────────────────────
    yield ProgressEvent("preflight", "Checking preflight...")

    if read_state() is not None:
        yield ProgressEvent(
            "preflight",
            "State file already exists — run deploy_down first (or delete deploy/.state.json if stale).",
            level="error",
        )
        return

    if not config.ssh_private_key.is_file():
        yield ProgressEvent(
            "preflight",
            f"SSH private key not found at {config.ssh_private_key}.",
            level="error",
        )
        return

    if not config.cloud_init_path.is_file():
        yield ProgressEvent(
            "preflight",
            f"cloud-init.yaml not found at {config.cloud_init_path}.",
            level="error",
        )
        return

    do = DOClient(config.do_api_token)

    yield ProgressEvent("preflight", f"Verifying DOMAIN={config.domain} is managed by DigitalOcean...")
    try:
        domain_ok = await do.domain_exists(config.domain)
    except Exception as exc:
        yield ProgressEvent(
            "preflight",
            f"Failed to query DO domain: {exc}",
            level="error",
        )
        return
    if not domain_ok:
        yield ProgressEvent(
            "preflight",
            f"Domain {config.domain} is not in this DigitalOcean account. "
            f"Add it at https://cloud.digitalocean.com/networking/domains or fix DOMAIN in .env.",
            level="error",
        )
        return

    # ── 2. create droplet ────────────────────────────────────────
    name = f"rc-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    yield ProgressEvent(
        "droplet",
        f"Creating droplet {name} ({config.do_size} in {config.do_region})...",
    )
    user_data = config.cloud_init_path.read_text()
    droplet_id, ip = await do.create_droplet(
        name=name,
        image=config.do_image,
        size=config.do_size,
        region=config.do_region,
        ssh_key_fp=config.do_ssh_key_fingerprint,
        user_data=user_data,
    )
    state = State(droplet_id=droplet_id, ip=ip, name=name, fqdn=config.fqdn)
    write_state(state)
    yield ProgressEvent(
        "droplet",
        f"Droplet ready: id={droplet_id} ip={ip}",
        droplet_id=droplet_id,
        ip=ip,
    )

    # ── 3. dns ───────────────────────────────────────────────────
    yield ProgressEvent(
        "dns",
        f"Upserting A-record {config.fqdn} -> {ip} (ttl={config.dns_ttl})",
        fqdn=config.fqdn,
        ip=ip,
    )
    await do.upsert_a_record(config.domain, config.subdomain, ip, config.dns_ttl)

    # ── 4. wait for ssh ──────────────────────────────────────────
    yield ProgressEvent("ssh", "Waiting for SSH...")
    await wait_for_ssh(ip, config.ssh_private_key)

    # ── 5. wait for cloud-init ───────────────────────────────────
    yield ProgressEvent("cloudinit", "Waiting for cloud-init (Docker install)...")
    await wait_for_cloud_init(ip, config.ssh_private_key)

    # ── 6. rsync ─────────────────────────────────────────────────
    yield ProgressEvent("rsync", "Preparing remote ~/app directory")
    await ssh_exec(ip, config.ssh_private_key, "mkdir -p ~/app/deploy")

    yield ProgressEvent("rsync", "Uploading server/")
    await rsync(
        config.repo_root / "server/",
        f"rc@{ip}:~/app/server/",
        config.ssh_private_key,
        delete=True,
        excludes=SERVER_EXCLUDES,
    )

    yield ProgressEvent("rsync", "Uploading web/")
    await rsync(
        config.repo_root / "web/",
        f"rc@{ip}:~/app/web/",
        config.ssh_private_key,
        delete=True,
        excludes=WEB_EXCLUDES,
    )

    yield ProgressEvent("rsync", "Uploading docker-compose.yml + Caddyfile")
    await rsync_files(
        [config.docker_compose_path, config.caddyfile_path],
        f"rc@{ip}:~/app/",
        config.ssh_private_key,
    )

    # ── 7. remote .env ───────────────────────────────────────────
    yield ProgressEvent("env", "Writing remote .env")
    env_body = _render_remote_env(config)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix="rc-env-", suffix=".env", delete=False
        ) as tmp:
            tmp.write(env_body)
            tmp_path = Path(tmp.name)
        await scp(tmp_path, f"rc@{ip}:~/app/.env", config.ssh_private_key)
        await ssh_exec(ip, config.ssh_private_key, "chmod 600 ~/app/.env")
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass

    # ── 8. docker compose ────────────────────────────────────────
    yield ProgressEvent("compose", "docker compose up -d --build (first build ~60s)...")
    await ssh_exec(
        ip,
        config.ssh_private_key,
        "cd ~/app && docker compose up -d --build",
    )

    # ── 9. health (warn-only) ────────────────────────────────────
    health_url = f"https://{config.fqdn}/api/health"
    yield ProgressEvent("health", f"Probing {health_url}...", fqdn=config.fqdn)
    ok = await wait_for_health(health_url)
    if ok:
        yield ProgressEvent("health", "Health OK", fqdn=config.fqdn)
    else:
        yield ProgressEvent(
            "health",
            f"Health never succeeded at {health_url} — check 'docker compose logs' on the droplet.",
            level="warn",
            fqdn=config.fqdn,
        )

    # ── 10. done ─────────────────────────────────────────────────
    yield ProgressEvent(
        "done",
        f"Deployment complete: https://{config.fqdn}",
        droplet_id=droplet_id,
        ip=ip,
        fqdn=config.fqdn,
    )

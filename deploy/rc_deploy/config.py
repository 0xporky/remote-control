from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

REQUIRED = [
    "DO_API_TOKEN",
    "DO_REGION",
    "DO_SIZE",
    "DO_IMAGE",
    "DO_SSH_KEY_FINGERPRINT",
    "DOMAIN",
    "SUBDOMAIN",
    "SECRET_KEY",
    "AUTH_PASSWORD",
    "GOOGLE_CLIENT_ID",
    "AGENT_TOKENS",
]


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeployConfig:
    do_api_token: str
    do_region: str
    do_size: str
    do_image: str
    do_ssh_key_fingerprint: str
    ssh_private_key: Path

    domain: str
    subdomain: str
    dns_ttl: int

    secret_key: str
    auth_password: str
    google_client_id: str
    agent_tokens: str
    agent_token_required: bool
    google_allowed_emails: str
    google_allowed_domains: str
    access_token_expire_minutes: int
    ws_session_timeout_seconds: int

    # Filled by load_config() — repo paths used elsewhere in the pipeline.
    repo_root: Path = field(default_factory=lambda: Path.cwd())
    deploy_dir: Path = field(default_factory=lambda: Path.cwd() / "deploy")

    @property
    def fqdn(self) -> str:
        return f"{self.subdomain}.{self.domain}"

    @property
    def cloud_init_path(self) -> Path:
        return self.deploy_dir / "cloud-init.yaml"

    @property
    def docker_compose_path(self) -> Path:
        return self.deploy_dir / "docker-compose.yml"

    @property
    def caddyfile_path(self) -> Path:
        return self.deploy_dir / "Caddyfile"


def _expand_key(path_str: str) -> Path:
    return Path(path_str).expanduser()


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def load_config(env_path: Path | None = None) -> DeployConfig:
    """Load deploy/.env into a DeployConfig. Raises ConfigError for missing/placeholder vars."""
    deploy_dir = (Path(__file__).resolve().parent.parent).resolve()
    repo_root = deploy_dir.parent
    env_file = env_path if env_path is not None else deploy_dir / ".env"

    if not env_file.is_file():
        raise ConfigError(f".env not found at {env_file}. Copy .env.example and fill in values.")

    raw = {k: (v or "") for k, v in dotenv_values(env_file).items()}

    missing = []
    placeholder = []
    for key in REQUIRED:
        val = raw.get(key, "").strip()
        if not val:
            missing.append(key)
        elif val.startswith("CHANGE_ME"):
            placeholder.append(key)

    if missing:
        raise ConfigError(f"Required vars missing in {env_file}: {', '.join(missing)}")
    if placeholder:
        raise ConfigError(
            f"Required vars still hold CHANGE_ME placeholders in {env_file}: {', '.join(placeholder)}"
        )

    ssh_key = _expand_key(raw.get("SSH_PRIVATE_KEY") or "~/.ssh/id_ed25519")

    return DeployConfig(
        do_api_token=raw["DO_API_TOKEN"].strip(),
        do_region=raw["DO_REGION"].strip(),
        do_size=raw["DO_SIZE"].strip(),
        do_image=raw["DO_IMAGE"].strip(),
        do_ssh_key_fingerprint=raw["DO_SSH_KEY_FINGERPRINT"].strip(),
        ssh_private_key=ssh_key,
        domain=raw["DOMAIN"].strip(),
        subdomain=raw["SUBDOMAIN"].strip(),
        dns_ttl=int(raw.get("DNS_TTL") or 60),
        secret_key=raw["SECRET_KEY"],
        auth_password=raw["AUTH_PASSWORD"],
        google_client_id=raw["GOOGLE_CLIENT_ID"].strip(),
        agent_tokens=raw["AGENT_TOKENS"],
        agent_token_required=_parse_bool(raw.get("AGENT_TOKEN_REQUIRED") or "true"),
        google_allowed_emails=raw.get("GOOGLE_ALLOWED_EMAILS") or "",
        google_allowed_domains=raw.get("GOOGLE_ALLOWED_DOMAINS") or "",
        access_token_expire_minutes=int(raw.get("ACCESS_TOKEN_EXPIRE_MINUTES") or 60),
        ws_session_timeout_seconds=int(raw.get("WS_SESSION_TIMEOUT_SECONDS") or 3600),
        repo_root=repo_root,
        deploy_dir=deploy_dir,
    )

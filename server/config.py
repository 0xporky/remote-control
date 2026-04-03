import os
import secrets
from typing import Optional

# Server settings
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# SSL/HTTPS settings
SSL_ENABLED: bool = os.getenv("SSL_ENABLED", "false").lower() == "true"
SSL_KEYFILE: Optional[str] = os.getenv("SSL_KEYFILE")  # Path to SSL key file
SSL_CERTFILE: Optional[str] = os.getenv("SSL_CERTFILE")  # Path to SSL certificate file

# Security settings
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production-use-a-strong-random-key")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Password for authentication (should be set via environment variable in production)
# This is the password users will enter to access the remote desktop
AUTH_PASSWORD: Optional[str] = os.getenv("AUTH_PASSWORD", "admin")

# Agent authorization tokens (comma-separated list of valid tokens)
# Agents must provide one of these tokens to register
# Generate tokens with: python -c "import secrets; print(secrets.token_urlsafe(32))"
AGENT_TOKENS: list[str] = [
    t.strip() for t in os.getenv("AGENT_TOKENS", "").split(",") if t.strip()
]
# If no tokens configured, allow any agent (for development)
AGENT_TOKEN_REQUIRED: bool = os.getenv("AGENT_TOKEN_REQUIRED", "false").lower() == "true"

# Rate limiting settings
RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = int(os.getenv("RATE_LIMIT_LOGIN_MAX_ATTEMPTS", "5"))
RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60"))
RATE_LIMIT_LOGIN_LOCKOUT_SECONDS: int = int(os.getenv("RATE_LIMIT_LOGIN_LOCKOUT_SECONDS", "300"))

# WebSocket settings
WS_SESSION_TIMEOUT_SECONDS: int = int(os.getenv("WS_SESSION_TIMEOUT_SECONDS", "3600"))  # 1 hour
WS_PING_INTERVAL_SECONDS: int = int(os.getenv("WS_PING_INTERVAL_SECONDS", "30"))
WS_PING_TIMEOUT_SECONDS: int = int(os.getenv("WS_PING_TIMEOUT_SECONDS", "10"))

# CORS settings
CORS_ORIGINS: list[str] = [
    origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()
]

# Google OAuth settings
GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
# Optional: Restrict to specific email domains (comma-separated)
GOOGLE_ALLOWED_DOMAINS: list[str] = [
    d.strip() for d in os.getenv("GOOGLE_ALLOWED_DOMAINS", "").split(",") if d.strip()
]
# Optional: Restrict to specific email addresses (comma-separated)
GOOGLE_ALLOWED_EMAILS: list[str] = [
    e.strip() for e in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",") if e.strip()
]

# Static files
WEB_CLIENT_PATH: str = os.getenv("WEB_CLIENT_PATH", "../web/dist")


def generate_agent_token() -> str:
    """Generate a secure random token for agent authorization."""
    return secrets.token_urlsafe(32)


def is_valid_agent_token(token: Optional[str]) -> bool:
    """Check if an agent token is valid."""
    if not AGENT_TOKEN_REQUIRED:
        return True
    if not token:
        return False
    return token in AGENT_TOKENS

"""Telegram-bot entrypoint for spinning the DigitalOcean stack up/down.

This is the Infra half of the split bot. It owns infrastructure lifecycle only —
provisioning the droplet and DNS A-record via `deploy/rc_deploy`. The local
desktop agent is started by the sibling Agent bot at `bot/agent/`, which runs
on a different machine; this bot hands off the credentials it needs via a
base64-encoded JSON blob in the /up success message.

Usage:
    cp .env.example .env  # fill in TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID
    python main.py

Reads ../../deploy/.env for DigitalOcean creds + DOMAIN + GOOGLE_CLIENT_ID. The
four dynamic vars (SUBDOMAIN, SECRET_KEY, AGENT_TOKENS, TURN_SECRET) are
generated fresh on every /up and may stay as CHANGE_ME_* placeholders in
deploy/.env.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

from handlers import Handlers, register

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot-infra")


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"Missing required env var: {name} (see bot/infra/.env.example)", file=sys.stderr)
        sys.exit(2)
    return val


def main() -> None:
    bot_dir = Path(__file__).resolve().parent
    load_dotenv(bot_dir / ".env")

    token = _require_env("TELEGRAM_BOT_TOKEN")
    try:
        allowed_user_id = int(_require_env("ALLOWED_TELEGRAM_USER_ID"))
    except ValueError:
        print("ALLOWED_TELEGRAM_USER_ID must be a numeric Telegram user id", file=sys.stderr)
        sys.exit(2)

    app = Application.builder().token(token).build()
    handlers = Handlers(allowed_user_id=allowed_user_id)
    register(app, handlers)

    logger.info("Infra bot starting (allowed user id %d)", allowed_user_id)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()

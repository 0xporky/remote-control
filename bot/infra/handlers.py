"""Telegram command/callback handlers for /up and /down (Infra bot).

The Infra bot owns infrastructure lifecycle only. On /up it provisions the
droplet, then emits a base64-encoded JSON credentials blob in the success
message so the user can paste it into the Agent bot to start the desktop
agent.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import secrets as secrets_module
import time
from dataclasses import replace
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import deploy_runner
import state

logger = logging.getLogger(__name__)

SUBDOMAIN_CHOICES = ("rc", "rc1", "rc2", "rc3")
_CB_PREFIX = "sub:"
_EDIT_MIN_INTERVAL_SECONDS = 2.0
_LINES_KEPT = 15

# Wire-format version for the base64 JSON blob handed to the Agent bot. Bump
# when the schema changes; the Agent bot rejects unknown versions.
_BLOB_VERSION = 1


class _ProgressEditor:
    """Owns one Telegram message and rewrites it in place from ProgressEvent stream.

    Throttled so we never edit faster than _EDIT_MIN_INTERVAL_SECONDS, except on
    stage changes and error-level events which always flush immediately.
    """

    def __init__(self, message, header: str):
        self._message = message
        self._header = header
        self._lines: list[str] = []
        self._last_stage: str | None = None
        self._last_edit_ts: float = 0.0

    async def __call__(self, evt) -> None:
        prefix = "❗" if evt.level == "error" else ("⚠️" if evt.level == "warn" else "•")
        self._lines.append(f"{prefix} [{evt.stage}] {evt.message}")
        if len(self._lines) > _LINES_KEPT:
            self._lines = self._lines[-_LINES_KEPT:]

        stage_changed = evt.stage != self._last_stage
        self._last_stage = evt.stage
        now = time.monotonic()
        elapsed = now - self._last_edit_ts
        if not (stage_changed or evt.level != "info" or elapsed >= _EDIT_MIN_INTERVAL_SECONDS):
            return
        self._last_edit_ts = now
        await self._flush()

    async def flush(self) -> None:
        self._last_edit_ts = time.monotonic()
        await self._flush()

    async def _flush(self) -> None:
        body = self._header + "\n" + "\n".join(self._lines)
        try:
            await self._message.edit_text(body)
        except BadRequest as exc:
            # Telegram raises BadRequest("Message is not modified") on identical edits.
            if "not modified" not in str(exc).lower():
                logger.warning("Failed to edit progress message: %s", exc)


def _encode_blob(*, subdomain: str, fqdn: str, agent_token: str, turn_secret: str) -> str:
    payload = {
        "v": _BLOB_VERSION,
        "sub": subdomain,
        "fqdn": fqdn,
        "agent_token": agent_token,
        "turn_secret": turn_secret,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


class Handlers:
    """Container so the long-running lock is shared across callbacks."""

    def __init__(self, *, allowed_user_id: int):
        self.allowed_user_id = allowed_user_id
        self._lock = asyncio.Lock()

    # ── auth ───────────────────────────────────────────────────────
    def _authorized(self, update: Update) -> bool:
        u = update.effective_user
        return u is not None and u.id == self.allowed_user_id

    # ── /up ────────────────────────────────────────────────────────
    async def cmd_up(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        existing = state.read_state()
        if existing is not None:
            await update.effective_chat.send_message(
                f"Already {existing.status} at https://{existing.fqdn}/ — run /down first."
            )
            return

        buttons = [
            [InlineKeyboardButton(text=sd, callback_data=f"{_CB_PREFIX}{sd}") for sd in SUBDOMAIN_CHOICES]
        ]
        await update.effective_chat.send_message(
            "Pick a subdomain:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def on_subdomain_choice(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        query = update.callback_query
        await query.answer()

        if not query.data or not query.data.startswith(_CB_PREFIX):
            return
        subdomain = query.data[len(_CB_PREFIX):]
        if subdomain not in SUBDOMAIN_CHOICES:
            await query.edit_message_text(f"Unknown subdomain: {subdomain}")
            return

        if self._lock.locked():
            await query.edit_message_text("Another operation is already in progress — try again later.")
            return

        async with self._lock:
            await self._run_up(update, subdomain)

    async def _run_up(self, update: Update, subdomain: str) -> None:
        chat = update.effective_chat
        # Re-check state inside the lock to avoid races.
        if state.read_state() is not None:
            await update.callback_query.edit_message_text("Deployment already in progress.")
            return

        sec = state.Secrets(
            secret_key=secrets_module.token_urlsafe(64),
            agent_tokens=secrets_module.token_urlsafe(32),
            turn_secret=secrets_module.token_urlsafe(32),
        )

        try:
            config = deploy_runner.build_config(subdomain, sec)
        except Exception as exc:
            await update.callback_query.edit_message_text(f"❌ Config error: {exc}")
            return

        fqdn = config.fqdn
        # Persist state BEFORE provisioning so a crash mid-deploy is recoverable via /down.
        state.write_state(state.BotState(
            status="deploying",
            subdomain=subdomain,
            fqdn=fqdn,
            secrets=sec,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        ))

        await update.callback_query.edit_message_text(f"🚀 Deploying to {fqdn}…")
        progress_msg = await chat.send_message(f"Starting deployment to {fqdn}…")
        editor = _ProgressEditor(progress_msg, header=f"🚀 Deploying to {fqdn}")

        try:
            ok = await deploy_runner.run_up(config, editor)
            await editor.flush()
        except Exception as exc:
            logger.exception("deploy_up raised")
            await chat.send_message(f"❌ Deploy crashed: {exc}\nState preserved — run /down to clean up.")
            return

        if not ok:
            await chat.send_message(
                f"❌ Deployment failed (error events above). State preserved — run /down to clean up."
            )
            return

        current = state.read_state()
        if current is not None:
            state.write_state(replace(current, status="up"))

        blob = _encode_blob(
            subdomain=subdomain,
            fqdn=fqdn,
            agent_token=sec.agent_tokens,
            turn_secret=sec.turn_secret,
        )
        await chat.send_message(
            f"✅ Deploy reached <b>done</b> at https://{fqdn}/\n\n"
            f"Start the agent on the Windows host: run /up on the Agent bot, "
            f"pick <b>{subdomain}</b>, then paste this blob:\n\n"
            f"<code>{blob}</code>",
            parse_mode=ParseMode.HTML,
        )

    # ── /down ──────────────────────────────────────────────────────
    async def cmd_down(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return

        existing = state.read_state()
        if existing is None:
            await update.effective_chat.send_message("Nothing to tear down (no state file).")
            return

        if self._lock.locked():
            await update.effective_chat.send_message("Another operation is already in progress — try again later.")
            return

        async with self._lock:
            await self._run_down(update, existing)

    async def _run_down(self, update: Update, current: state.BotState) -> None:
        chat = update.effective_chat
        state.write_state(replace(current, status="tearing_down"))

        try:
            config = deploy_runner.build_config(current.subdomain, current.secrets)
        except Exception as exc:
            await chat.send_message(f"❌ Config error: {exc}\nState left in place so you can fix .env and retry /down.")
            return

        progress_msg = await chat.send_message(f"Tearing down {current.fqdn}…")
        editor = _ProgressEditor(progress_msg, header=f"🧹 Tearing down {current.fqdn}")

        try:
            ok = await deploy_runner.run_down(config, editor)
            await editor.flush()
        except Exception as exc:
            logger.exception("deploy_down raised")
            await chat.send_message(f"❌ Teardown crashed: {exc}\nState preserved — retry /down.")
            return

        if not ok:
            await chat.send_message("❌ Teardown reported errors — state preserved so you can retry /down.")
            return

        state.clear_state()
        await chat.send_message("✅ Torn down. Compute billing stopped.")


def register(app: Application, handlers: Handlers) -> None:
    app.add_handler(CommandHandler("up", handlers.cmd_up))
    app.add_handler(CommandHandler("down", handlers.cmd_down))
    app.add_handler(CallbackQueryHandler(handlers.on_subdomain_choice, pattern=f"^{_CB_PREFIX}"))

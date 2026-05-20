"""Telegram command/callback handlers for /up and /down (Agent bot).

/up flow:
  1. User runs /up → subdomain picker (rc, rc1, rc2, rc3).
  2. Tap a subdomain → bot stores it in user_data["pending_up"] and prompts
     the user to paste the credentials blob from the Infra bot.
  3. Next text message → on_paste decodes the base64 JSON, validates the
     schema and the subdomain match, and spawns the agent via AgentRunner.

The catch-all MessageHandler must be registered AFTER the command handlers
so /up and /down aren't swallowed by it.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import state
from agent_runner import AgentRunner

logger = logging.getLogger(__name__)

SUBDOMAIN_CHOICES = ("rc", "rc1", "rc2", "rc3")
_CB_PREFIX = "sub:"
_PENDING_TTL_SECONDS = 300.0  # paste must arrive within 5 minutes of picker click
_TOKEN_CHARSET_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_FQDN_RE = re.compile(r"^[a-z0-9.\-]+$", re.IGNORECASE)
_EXPECTED_BLOB_VERSION = 1


def _decode_blob(raw: str) -> dict:
    """Decode and validate the paste blob. Raises ValueError with a user-readable message."""
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("empty blob")
    try:
        decoded = base64.urlsafe_b64decode(cleaned.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError(f"not valid base64 ({exc})") from exc
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError(f"decoded bytes are not JSON ({exc.msg})") from exc
    if not isinstance(payload, dict):
        raise ValueError("decoded JSON is not an object")

    v = payload.get("v")
    if v != _EXPECTED_BLOB_VERSION:
        raise ValueError(f"unsupported blob version {v!r} (expected {_EXPECTED_BLOB_VERSION})")

    required = ("sub", "fqdn", "agent_token", "turn_secret")
    missing = [k for k in required if not isinstance(payload.get(k), str) or not payload[k]]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")

    if not _FQDN_RE.match(payload["fqdn"]):
        raise ValueError("fqdn contains unexpected characters")
    if not _TOKEN_CHARSET_RE.match(payload["agent_token"]):
        raise ValueError("agent_token contains unexpected characters")
    if not _TOKEN_CHARSET_RE.match(payload["turn_secret"]):
        raise ValueError("turn_secret contains unexpected characters")

    return payload


class Handlers:
    """Container so the agent runner and the long-running lock are shared across callbacks."""

    def __init__(self, *, allowed_user_id: int, python_bin: str):
        self.allowed_user_id = allowed_user_id
        self.agent = AgentRunner(python_bin=python_bin)
        self._lock = asyncio.Lock()

    # ── auth ───────────────────────────────────────────────────────
    def _authorized(self, update: Update) -> bool:
        u = update.effective_user
        return u is not None and u.id == self.allowed_user_id

    # ── /up ────────────────────────────────────────────────────────
    async def cmd_up(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        existing = state.read_state()
        if existing is not None:
            await update.effective_chat.send_message(
                f"Agent already {existing.status} for https://{existing.fqdn}/ — run /down first."
            )
            return

        # Clear any stale pending paste; user is restarting the flow.
        ctx.user_data.pop("pending_up", None)

        buttons = [
            [InlineKeyboardButton(text=sd, callback_data=f"{_CB_PREFIX}{sd}") for sd in SUBDOMAIN_CHOICES]
        ]
        await update.effective_chat.send_message(
            "Pick a subdomain:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def on_subdomain_choice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
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

        if state.read_state() is not None:
            await query.edit_message_text("Agent is already running — run /down first.")
            return

        ctx.user_data["pending_up"] = {
            "subdomain": subdomain,
            "ts": time.monotonic(),
        }
        await query.edit_message_text(
            f"Picked <b>{subdomain}</b>. Now paste the credentials blob from the Infra bot "
            f"(times out in {int(_PENDING_TTL_SECONDS // 60)} min).",
            parse_mode=ParseMode.HTML,
        )

    async def on_paste(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return

        pending = ctx.user_data.get("pending_up")
        if not pending:
            # No pending /up — silently ignore arbitrary text so this bot doesn't
            # respond to every chat line.
            return

        if time.monotonic() - pending["ts"] > _PENDING_TTL_SECONDS:
            ctx.user_data.pop("pending_up", None)
            await update.effective_chat.send_message(
                "⏱ Paste timed out — run /up again to restart."
            )
            return

        text = (update.message.text or "").strip()
        try:
            payload = _decode_blob(text)
        except ValueError as exc:
            ctx.user_data.pop("pending_up", None)
            await update.effective_chat.send_message(
                f"❌ Blob rejected: {exc}\nRun /up again to retry."
            )
            return

        if payload["sub"] != pending["subdomain"]:
            ctx.user_data.pop("pending_up", None)
            await update.effective_chat.send_message(
                f"❌ Subdomain mismatch: picker said <b>{pending['subdomain']}</b> "
                f"but blob is for <b>{payload['sub']}</b>. Run /up again.",
                parse_mode=ParseMode.HTML,
            )
            return

        ctx.user_data.pop("pending_up", None)

        if self._lock.locked():
            await update.effective_chat.send_message(
                "Another operation is already in progress — try again later."
            )
            return

        async with self._lock:
            await self._start_agent(update, payload)

    async def _start_agent(self, update: Update, payload: dict) -> None:
        chat = update.effective_chat
        # Re-check state inside the lock to avoid races.
        if state.read_state() is not None:
            await chat.send_message("Agent is already running — run /down first.")
            return

        subdomain = payload["sub"]
        fqdn = payload["fqdn"]
        state.write_state(state.BotState(
            status="starting",
            subdomain=subdomain,
            fqdn=fqdn,
            agent_pid=None,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        ))

        await chat.send_message(f"Starting local agent for {fqdn}…")

        start = await self.agent.start(
            fqdn=fqdn,
            agent_token=payload["agent_token"],
            turn_secret=payload["turn_secret"],
        )

        if start.ok:
            current = state.read_state()
            if current is not None:
                state.write_state(replace(current, status="up", agent_pid=start.pid))
            await chat.send_message(f"✅ Ready: https://{fqdn}/")
        else:
            state.clear_state()
            tail = f"\n\n<pre>{_escape_html(start.tail)[-1500:]}</pre>" if start.tail else ""
            await chat.send_message(
                f"❌ {start.error}.{tail}",
                parse_mode=ParseMode.HTML,
            )

    # ── /down ──────────────────────────────────────────────────────
    async def cmd_down(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return

        # Clear any pending paste — /down supersedes an in-progress /up.
        ctx.user_data.pop("pending_up", None)

        existing = state.read_state()
        if existing is None:
            await update.effective_chat.send_message("Nothing to stop (no state file).")
            return

        if self._lock.locked():
            await update.effective_chat.send_message("Another operation is already in progress — try again later.")
            return

        async with self._lock:
            await self._run_down(update, existing)

    async def _run_down(self, update: Update, current: state.BotState) -> None:
        chat = update.effective_chat
        state.write_state(replace(current, status="stopping"))

        await chat.send_message(f"🛑 Stopping agent for {current.fqdn}…")
        await self.agent.stop(pid_from_state=current.agent_pid)
        state.clear_state()
        await chat.send_message("✅ Agent stopped. (Run /down on the Infra bot to tear down the droplet.)")


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def register(app: Application, handlers: Handlers) -> None:
    # Commands first — they must take precedence over the catch-all text handler.
    app.add_handler(CommandHandler("up", handlers.cmd_up))
    app.add_handler(CommandHandler("down", handlers.cmd_down))
    app.add_handler(CallbackQueryHandler(handlers.on_subdomain_choice, pattern=f"^{_CB_PREFIX}"))
    # Catch-all for the paste step. Registered last so it doesn't shadow /up or /down.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_paste))

# Agent Bot Development Guide

Technical reference for the Telegram bot that starts and stops the local desktop agent (`agent/main.py`). The sibling **Infra bot** at `bot/infra/` runs on a different machine and provisions the DigitalOcean infrastructure — this bot only manages the agent subprocess.

## Architecture Overview

```
┌──────────────────────────── Telegram ────────────────────────────┐
│                            python-telegram-bot                    │
│                              long-polling                         │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ Update
                       ┌───────────┴────────────┐
                       │      handlers.py       │
                       │   Handlers (auth,      │
                       │   lock, paste flow)    │
                       └────────────┬───────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │ agent_runner.py  │
                           │   AgentRunner    │
                           │  start / stop    │
                           └────────┬─────────┘
                                    │
                                    ▼
                           ┌──────────────────┐
                           │ agent/main.py    │
                           │  (subprocess)    │
                           └──────────────────┘

         state.py  →  bot/agent/.state.json   (survives bot restarts)
```

## File Map

| File | Purpose | Key Exports |
|------|---------|-------------|
| `main.py` | Entrypoint; reads `.env`, builds `Application`, runs polling. | `main()` |
| `handlers.py` | `/up`, `/down`, subdomain `CallbackQueryHandler`, paste `MessageHandler`. `asyncio.Lock` serializes commands. | `Handlers`, `register()`, `_decode_blob()` |
| `agent_runner.py` | Spawns and stops `agent/main.py`. Drains stdout, matches readiness regex, falls back to `psutil` to terminate by PID. | `AgentRunner`, `StartResult` |
| `state.py` | Atomic read/write/clear of `bot/agent/.state.json`. **No secrets persisted.** | `BotState`, `read_state()`, `write_state()`, `clear_state()` |
| `.env.example` | `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_ID`, `PYTHON_BIN`. | — |
| `requirements.txt` | `python-telegram-bot>=21,<22`, `psutil`, `python-dotenv`. **No** dependency on `deploy/`. | — |
| `.gitignore` | Excludes `.env`, `.state.json`, `__pycache__/`, `.venv/`. | — |

## Key Flows

### `/up` (two-step: picker → paste)

1. **Auth** — `Handlers._authorized()` checks `update.effective_user.id == ALLOWED_TELEGRAM_USER_ID`. Mismatched users get no reply.
2. **State guard** — refuse if `bot/agent/.state.json` already exists.
3. **Subdomain picker** — `InlineKeyboardMarkup` with `rc | rc1 | rc2 | rc3`. Callback data: `sub:<sd>`.
4. **Callback** — `on_subdomain_choice` stores `ctx.user_data["pending_up"] = {"subdomain": …, "ts": time.monotonic()}` and prompts: *"Now paste the credentials blob…"*. The reply uses HTML, not Markdown.
5. **Paste handler** (`MessageHandler(filters.TEXT & ~filters.COMMAND, …)`):
   - If no `pending_up` → silently ignore (so this bot doesn't reply to random chat text).
   - If `time.monotonic() - pending_up["ts"] > 300s` → tell user it timed out, clear pending.
   - `_decode_blob()` base64-decodes, parses JSON, validates schema (`v == 1`, required fields, charset of token fields, FQDN shape).
   - Verify `payload["sub"] == pending_up["subdomain"]` to catch picker/blob mismatches.
   - Enter `asyncio.Lock`, write state `status="starting"`, call `AgentRunner.start(fqdn, agent_token, turn_secret)`, wait ≤30 s for readiness regex `r"Registered as agent"`.
   - On success → update state with `status="up"` and `agent_pid`. On failure → `clear_state()` and post the stdout tail (HTML-escaped, truncated to 1500 chars).
   - Always clear `pending_up` before exiting (success or failure).

### `/down`

1. Read state; if absent, say "nothing to stop".
2. Lock. Re-tag state as `stopping`.
3. **Stop agent** — `AgentRunner.stop(pid_from_state=…)`:
   - If the in-memory `asyncio.subprocess.Process` is still alive → `terminate()` then `kill()` after 5 s.
   - Else (bot was restarted since `/up`) → `psutil.Process(pid).terminate()` + same fallback.
4. `clear_state()`.

**This bot does not touch infrastructure.** After stopping the agent, run `/down` on the Infra bot separately to tear the droplet down. Recommended order: this bot's `/down` first, then Infra's.

### Concurrency model

A single `asyncio.Lock` on `Handlers` serializes all agent-lifecycle work. The picker→paste flow uses `ctx.user_data` (built into python-telegram-bot v21) for per-chat correlation — simpler than `ConversationHandler` for a two-step exchange.

## Paste-blob contract

The Infra bot emits a base64-urlsafe-encoded JSON payload in its `/up` success message:

```json
{
  "v": 1,
  "sub": "rc1",
  "fqdn": "rc1.example.com",
  "agent_token": "<urlsafe base64>",
  "turn_secret": "<urlsafe base64>"
}
```

`_decode_blob()` in `handlers.py` is the source of truth for accepted blobs on this side. If the Infra bot bumps `_BLOB_VERSION`, update `_EXPECTED_BLOB_VERSION` here in the same change.

**Secrets are runtime-only.** `agent_token` and `turn_secret` live only in `ctx.user_data` (cleared as soon as the agent starts or fails) and as command-line arguments to the agent subprocess (visible in `ps`). They are deliberately **not** written to `bot/agent/.state.json` — restarting this bot mid-cycle forces a re-paste, which is fine.

## Cross-component contracts

- **Agent CLI flags** — `agent_runner.py:AgentRunner.start()` builds:
  ```
  agent/main.py --server=wss://{fqdn}/ws/signaling --token=… --turn-urls=turn:{fqdn}:3478?transport=udp,turn:{fqdn}:3478?transport=tcp --turn-secret=…
  ```
  Mirrors `agent/config.py`. If you rename any flag, update here too.
- **Readiness signal** — `_READY_RE = r"Registered as agent"`. Sourced from `agent/signaling.py:83` (`logger.info(f"Registered as agent: {self.config.agent_id}")`). If you change that log line, also update the regex or the agent won't be detected as "ready" and the bot will report a timeout.
- **Bot state schema** — `bot/agent/.state.json` is owned by `state.py` only. Other components must not read or write it.

## State file

```
bot/agent/.state.json    ← bot-owned, holds {status, subdomain, fqdn, agent_pid, started_at}
```

Gitignored. Cleared after `/down`. If the bot was killed mid-`/up` and never reached `status="up"`, you may end up with `status="starting"` on disk — delete the file manually, then `/up` again.

## Handler registration order (important)

`register()` adds handlers in this order:
1. `CommandHandler("up", …)`
2. `CommandHandler("down", …)`
3. `CallbackQueryHandler(…, pattern="^sub:")`
4. `MessageHandler(filters.TEXT & ~filters.COMMAND, on_paste)` — **last**.

The `MessageHandler` is the catch-all for the paste step. If you register it before the command handlers, `/up`/`/down` will be swallowed as text. python-telegram-bot evaluates handlers in registration order within a group; keep the catch-all last.

## Debugging

### Bot is silent after a button tap

- Confirm `ALLOWED_TELEGRAM_USER_ID` matches the user who tapped. Bot returns silently on mismatch.
- Check the bot's stdout for tracebacks.

### Bot silently ignores my paste

- You must run `/up` and pick a subdomain first — pasting a blob with no `pending_up` is silently ignored.
- The paste must arrive within 5 minutes of the picker click. After that, send `/up` again.

### Agent never reports ready

```python
# in bot/agent/agent_runner.py
_READY_TIMEOUT_SECONDS = 30.0   # bump if your server takes longer to accept WS
_READY_RE = re.compile(r"Registered as agent", re.IGNORECASE)
```

Tail the agent output manually:
```
cd agent
python main.py --server=wss://<fqdn>/ws/signaling --token=<agent_token> --turn-urls=… --turn-secret=…
```

### Stuck `starting` / `stopping` state

Edit (or delete) `bot/agent/.state.json`. If a stray agent process is still running, kill it with `Get-Process python` / `taskkill /PID …` on Windows.

### python-telegram-bot version

Pinned to `>=21,<22`. v21 is async-native; earlier versions used a different `Updater`/`Dispatcher` API and the handler signatures here won't work.

## Extending

- **New subdomain options** — edit `SUBDOMAIN_CHOICES` in `handlers.py`. Keep this list in sync with `bot/infra/handlers.py:SUBDOMAIN_CHOICES` so the picker on the Infra side matches.
- **Additional fields in the paste blob** — bump `_EXPECTED_BLOB_VERSION` and extend `_decode_blob`. Coordinate with `bot/infra/handlers.py:_encode_blob` in the same change.
- **More commands** — add `CommandHandler("name", handlers.cmd_name)` in `handlers.py:register()` **before** the catch-all `MessageHandler`. Wrap each handler with the `_authorized` check.

# Infra Bot Development Guide

Technical reference for the Telegram bot that orchestrates `deploy_up` / `deploy_down`. The sibling **Agent bot** at `bot/agent/` runs on a different machine and is responsible for spawning the desktop agent — this bot only provisions infrastructure.

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
                       │   lock, progress)      │
                       └───┬────────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ deploy_runner.py │
                  │  build_config    │
                  │  run_up/run_down │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  rc_deploy       │
                  │  (async gen)     │
                  └──────────────────┘

         state.py  →  bot/infra/.state.json   (survives bot restarts)
```

## File Map

| File | Purpose | Key Exports |
|------|---------|-------------|
| `main.py` | Entrypoint; reads `.env`, builds `Application`, runs polling. | `main()` |
| `handlers.py` | `/up`, `/down`, subdomain `CallbackQueryHandler`. Single `asyncio.Lock` serializes commands. Emits the base64 JSON blob on success. | `Handlers`, `register()`, `_ProgressEditor`, `_encode_blob()` |
| `deploy_runner.py` | Inserts `deploy/` on `sys.path`, imports `rc_deploy`, builds `DeployConfig` with overrides, streams events. | `build_config()`, `run_up()`, `run_down()` |
| `state.py` | Atomic read/write/clear of `bot/infra/.state.json`. | `BotState`, `Secrets`, `read_state()`, `write_state()`, `clear_state()` |
| `.env.example` | `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_ID`. | — |
| `requirements.txt` | Chains `../../deploy/requirements.txt` + `python-telegram-bot>=21,<22`. | — |
| `.gitignore` | Excludes `.env`, `.state.json`, `__pycache__/`, `.venv/`. | — |

## Key Flows

### `/up`

1. **Auth** — `Handlers._authorized()` checks `update.effective_user.id == ALLOWED_TELEGRAM_USER_ID`. Mismatched users get no reply.
2. **State guard** — refuse if `bot/infra/.state.json` exists.
3. **Subdomain picker** — `InlineKeyboardMarkup` with `rc | rc1 | rc2 | rc3`. Callback data: `sub:<sd>`.
4. **Callback** — `on_subdomain_choice` enters `asyncio.Lock`, re-checks state, then:
   - Generates `Secrets` via `secrets.token_urlsafe(64|32|32)` (fresh every time, no env fallback).
   - Persists `BotState(status="deploying", …)` **before** any DO call so a crash is recoverable.
   - Calls `deploy_runner.build_config(subdomain, secrets)` → `load_config(overrides=…)`.
   - Iterates `deploy_up(config)`; `_ProgressEditor` edits a single Telegram message in place, throttled to ≥2 s between edits (immediate on stage change or error level).
   - On success, updates state to `status="up"` and sends the credentials blob (base64-encoded JSON, see [Paste-blob contract](#paste-blob-contract)) wrapped in a `<code>` tag for tap-to-copy.
5. **Failure modes**:
   - Error events during `deploy_up` → state preserved; user must `/down`.
   - Config error before deploy starts → state never written; reply with the error.

### `/down`

1. Read state; if absent, say "nothing to tear down".
2. Lock. Re-tag state as `tearing_down`.
3. Build the same `DeployConfig` (secrets read from state, not regenerated).
4. Iterate `deploy_down(config, clear_dns=True)`. Stream to a single message.
5. On success → `clear_state()`. On error → leave state intact for retry.

**This bot does not touch the desktop agent.** If the user runs `/down` here while the Agent bot's agent is still running, the agent's websocket will die when the droplet vanishes. The user must run `/down` on the Agent bot separately to stop the local process. Recommended order: Agent `/down` first, then Infra `/down`.

### Concurrency model

A single `asyncio.Lock` on `Handlers` serializes all command work. The `if self._lock.locked(): …` fast-path is a UX nicety (rejects immediately rather than queueing); correctness relies on the `async with self._lock` acquire.

## Paste-blob contract

The credentials handoff between the Infra and Agent bots is a base64-urlsafe-encoded JSON payload:

```json
{
  "v": 1,
  "sub": "rc1",
  "fqdn": "rc1.example.com",
  "agent_token": "<urlsafe base64>",
  "turn_secret": "<urlsafe base64>"
}
```

`SECRET_KEY` is deliberately **not** in the blob — it never leaves this machine. If you change this schema, bump `_BLOB_VERSION` in `handlers.py` and update the Agent bot's validator at `bot/agent/handlers.py:_decode_blob()` in the same change.

## Cross-component contracts

- **Deploy config override** — `deploy/rc_deploy/config.py:74` `load_config(env_path=None, overrides=None)`. The bot supplies `{"SUBDOMAIN", "SECRET_KEY", "AGENT_TOKENS", "TURN_SECRET"}` so `.env` can leave these as `CHANGE_ME_*`. If you change the required-vars set in `config.py:REQUIRED`, audit `bot/infra/deploy_runner.py:build_config`.
- **Bot state schema** — `bot/infra/.state.json` is owned by `state.py` only. Other components must not read or write it. The deploy module has its own `deploy/.state.json` (droplet id / ip / fqdn) — left untouched.

## State Files

```
bot/infra/.state.json  ← bot-owned, holds runtime secrets, cleared after /down
deploy/.state.json     ← deploy-owned, holds droplet_id / ip / name / fqdn
```

Both are gitignored. If they get out of sync (e.g. you ran `deploy.py up` outside the bot), `deploy_up`'s preflight check will refuse with *"State file already exists"* — clean up `deploy/.state.json` manually.

## Debugging

### Bot is silent after a button tap

- Confirm `ALLOWED_TELEGRAM_USER_ID` matches the user who tapped. Bot returns silently on mismatch.
- Check the bot's stdout for tracebacks — `deploy_runner.build_config` raising will surface as `Config error:` in chat, but unexpected exceptions before the chat message exists land only in the log.

### Stuck `deploying` / `tearing_down` state

Edit (or delete) `bot/infra/.state.json`. If a droplet was actually created, also reconcile `deploy/.state.json` and the DO dashboard.

### Agent bot rejects the blob

If the user reports the Agent bot says the blob is malformed, sanity-check that Telegram didn't wrap the code block with extra whitespace — the Agent bot is strict about base64 padding. Re-send by running `/up` again to regenerate fresh secrets.

### python-telegram-bot version

Pinned to `>=21,<22`. v21 is async-native; earlier versions used a different `Updater`/`Dispatcher` API and the handler signatures here won't work.

## Extending

- **New subdomain options** — edit `SUBDOMAIN_CHOICES` in `handlers.py`. The inline keyboard rebuilds automatically. Keep this list in sync with `bot/agent/handlers.py:SUBDOMAIN_CHOICES` so the picker on the Agent side matches.
- **Additional fields in the paste blob** — bump `_BLOB_VERSION`, extend `_encode_blob`, and update the Agent bot's `_decode_blob` validator at the same time.
- **More commands** — add `CommandHandler("name", handlers.cmd_name)` in `handlers.py:register()`. Wrap each handler with the `_authorized` check.
- **Per-deploy notes** — extend `state.BotState` with new optional fields. `state.write_state` handles unknown keys via `asdict`, but `read_state` is strict — add explicit `data.get(...)` reads.

# Bot Development Guide

Technical reference for the Telegram bot that orchestrates `deploy_up` / `deploy_down` and the local agent process.

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
                       └───┬────────────┬───────┘
                           │            │
            ┌──────────────┘            └───────────────┐
            ▼                                            ▼
   ┌──────────────────┐                       ┌──────────────────┐
   │ deploy_runner.py │                       │ agent_runner.py  │
   │  build_config    │                       │   AgentRunner    │
   │  run_up/run_down │                       │  start / stop    │
   └────────┬─────────┘                       └────────┬─────────┘
            │                                          │
            ▼                                          ▼
   ┌──────────────────┐                       ┌──────────────────┐
   │  rc_deploy       │                       │ agent/main.py    │
   │  (async gen)     │                       │  (subprocess)    │
   └──────────────────┘                       └──────────────────┘

         state.py  →  bot/.state.json   (survives bot restarts)
```

## File Map

| File | Purpose | Key Exports |
|------|---------|-------------|
| `main.py` | Entrypoint; reads `.env`, builds `Application`, runs polling. | `main()` |
| `handlers.py` | `/up`, `/down`, subdomain `CallbackQueryHandler`. Single `asyncio.Lock` serializes commands. | `Handlers`, `register()`, `_ProgressEditor` |
| `deploy_runner.py` | Inserts `deploy/` on `sys.path`, imports `rc_deploy`, builds `DeployConfig` with overrides, streams events. | `build_config()`, `run_up()`, `run_down()` |
| `agent_runner.py` | Spawns and stops `agent/main.py`. Drains stdout, matches readiness regex, falls back to `psutil` to terminate by PID. | `AgentRunner`, `StartResult` |
| `state.py` | Atomic read/write/clear of `bot/.state.json`. | `BotState`, `Secrets`, `read_state()`, `write_state()`, `clear_state()` |
| `.env.example` | `TELEGRAM_BOT_TOKEN`, `ALLOWED_TELEGRAM_USER_ID`, `PYTHON_BIN`. | — |
| `requirements.txt` | Chains `deploy/requirements.txt` + `python-telegram-bot>=21,<22` + `psutil`. | — |
| `.gitignore` | Excludes `.env`, `.state.json`, `__pycache__/`, `.venv/`. | — |

## Key Flows

### `/up`

1. **Auth** — `Handlers._authorized()` checks `update.effective_user.id == ALLOWED_TELEGRAM_USER_ID`. Mismatched users get no reply.
2. **State guard** — refuse if `bot/.state.json` exists.
3. **Subdomain picker** — `InlineKeyboardMarkup` with `rc | rc1 | rc2 | rc3`. Callback data: `sub:<sd>`.
4. **Callback** — `on_subdomain_choice` enters `asyncio.Lock`, re-checks state, then:
   - Generates `Secrets` via `secrets.token_urlsafe(64|32|32)` (fresh every time, no env fallback).
   - Persists `BotState(status="deploying", …)` **before** any DO call so a crash is recoverable.
   - Calls `deploy_runner.build_config(subdomain, secrets)` → `load_config(overrides=…)`.
   - Iterates `deploy_up(config)`; `_ProgressEditor` edits a single Telegram message in place, throttled to ≥2 s between edits (immediate on stage change or error level).
   - On success, spawns the agent via `AgentRunner.start()` and waits ≤30 s for the readiness regex `r"Registered as agent"`.
   - Updates state to `status="up"` with the agent PID.
5. **Failure modes**:
   - Error events during `deploy_up` → state preserved; user must `/down`.
   - Agent process exits before ready → posts the last ~30 lines of stdout (HTML-escaped, truncated to 1500 chars).
   - Agent timeout → kills the process, posts an error.

### `/down`

1. Read state; if absent, say "nothing to tear down".
2. Lock. Re-tag state as `tearing_down`.
3. **Stop agent** — `AgentRunner.stop(pid_from_state=…)`:
   - If the in-memory `asyncio.subprocess.Process` is still alive → `terminate()` then `kill()` after 5 s.
   - Else (bot was restarted since `/up`) → `psutil.Process(pid).terminate()` + same fallback.
4. Build the same `DeployConfig` (secrets read from state, not regenerated).
5. Iterate `deploy_down(config, clear_dns=True)`. Stream to a single message.
6. On success → `clear_state()`. On error → leave state intact for retry.

### Concurrency model

A single `asyncio.Lock` on `Handlers` serializes all command work. The `if self._lock.locked(): …` fast-path is a UX nicety (rejects immediately rather than queueing); correctness relies on the `async with self._lock` acquire.

## Cross-component contracts

- **Deploy config override** — `deploy/rc_deploy/config.py:74` `load_config(env_path=None, overrides=None)`. The bot supplies `{"SUBDOMAIN", "SECRET_KEY", "AGENT_TOKENS", "TURN_SECRET"}` so `.env` can leave these as `CHANGE_ME_*`. If you change the required-vars set in `config.py:REQUIRED`, audit `bot/deploy_runner.py:build_config`.
- **Agent CLI flags** — `bot/agent_runner.py:AgentRunner.start()` builds:
  ```
  agent/main.py --server=wss://{fqdn}/ws/signaling --token=… --turn-urls=turn:{fqdn}:3478?transport=udp,turn:{fqdn}:3478?transport=tcp --turn-secret=…
  ```
  Mirrors `agent/config.py`. If you rename any flag, update both.
- **Readiness signal** — `_READY_RE = r"Registered as agent"`. Sourced from `agent/signaling.py:83` (`logger.info(f"Registered as agent: {self.config.agent_id}")`). If you change that log line, also update the regex or the agent won't be detected as "ready" and the bot will report a timeout.
- **Bot state schema** — `bot/.state.json` is owned by `state.py` only. Other components must not read or write it. The deploy module has its own `deploy/.state.json` (droplet id / ip / fqdn) — left untouched.

## State Files

```
bot/.state.json    ← bot-owned, holds runtime secrets + agent PID, cleared after /down
deploy/.state.json ← deploy-owned, holds droplet_id / ip / name / fqdn, cleared by deploy_down
```

Both are gitignored. If they get out of sync (e.g. you ran `deploy.py up` outside the bot), `deploy_up`'s preflight check will refuse with *"State file already exists"* — clean up `deploy/.state.json` manually.

## Debugging

### Bot is silent after a button tap

- Confirm `ALLOWED_TELEGRAM_USER_ID` matches the user who tapped. Bot returns silently on mismatch.
- Check the bot's stdout for tracebacks — `deploy_runner.build_config` raising will surface as `Config error:` in chat, but unexpected exceptions before the chat message exists land only in the log.

### Agent never reports ready

```python
# in bot/agent_runner.py
_READY_TIMEOUT_SECONDS = 30.0   # bump if your server takes longer to accept WS
_READY_RE = re.compile(r"Registered as agent", re.IGNORECASE)
```

Tail the agent output manually:
```
cd agent
python main.py --server=wss://<fqdn>/ws/signaling --token=<agent_token> --turn-urls=… --turn-secret=…
```

### Stuck `deploying` / `tearing_down` state

Edit (or delete) `bot/.state.json`. If a droplet was actually created, also reconcile `deploy/.state.json` and DO dashboard.

### python-telegram-bot version

Pinned to `>=21,<22`. v21 is async-native; earlier versions used a different `Updater`/`Dispatcher` API and the handler signatures here won't work.

## Extending

- **New subdomain options** — edit `SUBDOMAIN_CHOICES` in `bot/handlers.py`. The inline keyboard rebuilds automatically.
- **More commands** — add `CommandHandler("name", handlers.cmd_name)` in `bot/handlers.py:register()`. Wrap each handler with the `_authorized` check.
- **Per-deploy notes** — extend `state.BotState` with new optional fields. `state.write_state` handles unknown keys via `asdict`, but `read_state` is strict — add explicit `data.get(...)` reads.
- **Multiple users** — replace `_authorized` with a set membership check; switch the single `asyncio.Lock` to a per-deployment scheme if you want parallel deploys to different subdomains.

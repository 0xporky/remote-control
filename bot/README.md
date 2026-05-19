# Remote Control Telegram Bot

Single-user Telegram bot that brings the DigitalOcean droplet up on demand and tears it down when you're done — so you only pay for compute while you're actually using the remote desktop.

```
Telegram → bot (Windows host) → DigitalOcean (server + web)
                              → local agent (screen capture)
```

Two commands:

- **`/up`** — pick a subdomain, generate fresh `SECRET_KEY` / `AGENT_TOKENS` / `TURN_SECRET`, run `deploy/deploy.py up`, then start the local agent.
- **`/down`** — stop the agent and tear the droplet (and DNS A-record) back down.

The bot is locked to a single Telegram user id and runs on the Windows host that hosts the agent (it needs to spawn `python agent/main.py` locally).

---

## Install

Run all commands from this directory (`bot/`).

### 1. Prerequisites

- Python **3.11** on PATH.
- `deploy/.env` already filled in with real DigitalOcean + DOMAIN + GOOGLE_CLIENT_ID values (see `deploy/.env.example`). The four runtime vars (`SUBDOMAIN`, `SECRET_KEY`, `AGENT_TOKENS`, `TURN_SECRET`) can stay as `CHANGE_ME_*` placeholders — the bot generates them per deploy.
- The `agent/` Python venv already set up (with `ffmpeg@7`/PyAV) so the agent process the bot spawns can actually run. See `agent/README` or `AGENT_SET.md`.

### 2. Create a Telegram bot

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, follow the prompts. Copy the bot token.
2. Talk to [@userinfobot](https://t.me/userinfobot). Copy your numeric user id.

### 3. Set up the bot venv

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
**Windows (CMD):**
```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pulls in `python-telegram-bot`, `psutil`, plus everything in `deploy/requirements.txt` (`pydo`, `python-dotenv`, `httpx`) so it can import `rc_deploy` directly.

### 4. Configure

```
copy .env.example .env       # Windows
cp .env.example .env         # macOS/Linux
```

Fill in `.env`:

| Var | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `ALLOWED_TELEGRAM_USER_ID` | Your numeric user id (no one else can use the bot) |
| `PYTHON_BIN` | *(optional)* Python used to spawn the agent. Defaults to the bot's own interpreter. Point this at the agent venv's `python.exe` if the agent has its own venv. |

---

## Run

```
python main.py
```

Output should be:

```
INFO bot: Bot starting (allowed user id 123456789, agent python: …)
```

The bot polls Telegram — there's no webhook, so you don't need an inbound port. Leave the terminal open (or run under NSSM / a Scheduled Task / `tmux` to keep it alive).

---

## Using it

In a chat with your bot:

1. **`/up`** — bot replies with a keyboard of `rc | rc1 | rc2 | rc3`. Tap one.
2. Watch a single message edit in place through the deploy stages: `preflight → droplet → dns → ssh → cloudinit → rsync → env → compose → health → done`. Total time ≈ 5–10 min on a first build.
3. The bot then spawns the agent locally. When it sees `Registered as agent: …` in the agent's logs (within 30 s) you'll get **`✅ Ready: https://<sub>.<domain>/`**.
4. Open that URL in a browser, sign in with Google, and the screen of the Windows host should stream.
5. When you're done, **`/down`** — the bot stops the agent, runs `deploy_down`, removes the DNS record, and clears its state.

Edge cases the bot handles:

- `/up` while a deployment already exists → refuses; you must `/down` first.
- Bot restarts mid-cycle → state is on disk (`bot/.state.json`), so `/down` still works (PID is recovered via `psutil`).
- Agent fails to register within 30 s → bot reports the failure with the last lines of the agent log; the droplet stays up so you can investigate and then `/down`.

---

## Files this directory writes at runtime

| File | Purpose | Gitignored |
|------|---------|------------|
| `.env` | bot token + allowed user id | ✓ |
| `.state.json` | current `status`, `subdomain`, `fqdn`, generated secrets, agent PID. Cleared at the end of `/down`. | ✓ |
| `__pycache__/` | normal Python cache | ✓ |

Secrets generated for one deploy are **never reused** — every `/up` rolls fresh values, and `/down` deletes them from disk.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Bot starts but `/up` does nothing | Wrong `ALLOWED_TELEGRAM_USER_ID`. Bot silently ignores other users. |
| `ConfigError: Required vars missing in deploy/.env` | Fill in `DO_API_TOKEN`, `DOMAIN`, `GOOGLE_CLIENT_ID`, `DO_SSH_KEY_FINGERPRINT`, etc. |
| `Agent did not register within 30s; killed` | Server may not be ready (health check failed silently) or token mismatch. Try opening `https://<fqdn>/api/health` in a browser; check `docker compose logs` on the droplet. |
| `Failed to spawn agent: [WinError 2]` | `PYTHON_BIN` doesn't point at a real Python interpreter. |
| Bot prints nothing after `/up` button tap | Either `deploy/.env` is missing or another operation is in progress. Check the bot's own console output for stack traces. |

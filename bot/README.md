# Remote Control Telegram Bots

This directory contains **two independent Telegram bots** that together let you bring the remote-desktop stack up and down from a phone — so you only pay for compute while you're actually using it.

```
Telegram → bot/infra (Linux host)   → DigitalOcean droplet (server + web + coturn)
Telegram → bot/agent (Windows host) → local agent (screen capture)
```

They run on different machines and share no filesystem. The Infra bot generates per-deploy secrets and prints a base64-encoded JSON credentials blob in its `/up` success message; the user copy-pastes that blob into the Agent bot to start the desktop agent against the freshly-provisioned droplet.

| Bot | Where it runs | What it does |
|-----|--------------|--------------|
| [`infra/`](infra/) | Linux host with DigitalOcean creds | `/up` → pick subdomain → provision droplet + DNS → emit credentials blob. `/down` → tear it all down. |
| [`agent/`](agent/) | Windows desktop being controlled | `/up` → pick subdomain → paste the blob → start `agent/main.py`. `/down` → stop the agent. |

## Setup at a glance

Read each bot's own README/CLAUDE.md for the full details:

- [`bot/infra/CLAUDE.md`](infra/CLAUDE.md) — architecture, deploy flow, blob format (producer side).
- [`bot/agent/CLAUDE.md`](agent/CLAUDE.md) — architecture, paste flow, blob format (consumer side).
- [`bot/CLAUDE.md`](CLAUDE.md) — the cross-bot contract.

### Quick path

**On the Linux host (bare metal / venv):**

```bash
cd bot/infra
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID
# Make sure ../../deploy/.env has DigitalOcean + DOMAIN + GOOGLE_CLIENT_ID
python main.py
```

**On the Linux host (Docker, Alpine-based):**

The image bakes in the repo code that gets rsynced to the droplet (`server/`, `web/`, `deploy/`). Secrets — `.env` files and the SSH private key — are bind-mounted at runtime so they stay out of the image. Build context is the repo root.

```bash
# From the repo root
docker build -t rc-infra-bot -f bot/infra/Dockerfile .
```

In `deploy/.env`, set `DO_SSH_KEY_PATH` to the **container** path you'll mount the key at (e.g. `/run/secrets/id_ed25519`), not the host path.

```bash
docker run -d --name rc-infra-bot --restart unless-stopped \
  -v "$HOME/.ssh/id_ed25519:/run/secrets/id_ed25519:ro" \
  rc-infra-bot
```

Notes:

- `.state.json` lives in the container's writable layer — survives `docker restart` / `docker stop && docker start`, but `docker rm` wipes it. Don't pass `--rm` to `docker run`. If you must recreate the container while a deploy is live, write down the FQDN and use the DigitalOcean dashboard to tear it down manually.
- Tail logs: `docker logs -f rc-infra-bot`.
- Rebuild whenever `server/`, `web/`, or `deploy/` changes — those files are baked into the image at build time.
- The repo-root `.dockerignore` keeps `.env`, `.state.json`, `.venv/`, `__pycache__/`, and `node_modules/` out of the build context.

**On the Windows host:**
It is steps how to run agent via cmd on Windows.

```powershell
cd bot\agent
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # fill in TELEGRAM_BOT_TOKEN (a DIFFERENT BotFather bot), ALLOWED_TELEGRAM_USER_ID, PYTHON_BIN
python main.py
```

Each bot needs its own BotFather bot (talk to [@BotFather](https://t.me/BotFather) twice). Both `.env` files use the **same** `ALLOWED_TELEGRAM_USER_ID` — the numeric id of whoever is going to talk to them.

## Using it

1. In a chat with the **Infra bot**: `/up` → pick a subdomain → watch the deploy stages stream → copy the `<code>…</code>` blob from the success message.
2. In a chat with the **Agent bot**: `/up` → pick the **same** subdomain → paste the blob.
3. Open `https://<sub>.<domain>/` in a browser, sign in with Google, and the Windows desktop should stream.
4. When done: Agent bot `/down` → Infra bot `/down`. In that order, so the agent isn't reconnecting against a vanishing droplet.

## Turning the laptop screen off while leaving the agent running

When you want to leave the Windows laptop on (so you can reconnect later) but don't need the physical panel lit, run on the Windows host:

```powershell
nircmd.exe monitor off
```

Get `nircmd.exe` from https://www.nirsoft.net/utils/nircmd.html and put it on `PATH` (or invoke with a full path).

Notes:

- The agent keeps capturing — Windows still composes the desktop into the framebuffer, so the WebRTC stream is unaffected.
- The first mouse or key event you send from the browser counts as user input and wakes the panel back on.
- Make sure auto-lock / "require sign-in on wake" is disabled in Windows. The agent runs in user-mode and cannot reach the lock screen, so if the panel wakes into a lock prompt you'll be stuck.

## Files each bot writes at runtime

| File | Bot | Contents | Gitignored |
|------|-----|----------|------------|
| `infra/.env` | Infra | bot token + allowed user id | ✓ |
| `infra/.state.json` | Infra | status, subdomain, fqdn, **generated secrets** (full triple) | ✓ |
| `agent/.env` | Agent | bot token + allowed user id + python bin | ✓ |
| `agent/.state.json` | Agent | status, subdomain, fqdn, **agent_pid** — no secrets | ✓ |

The Agent bot deliberately does not persist secrets — tokens are runtime-only and the user re-pastes the blob if the bot is restarted mid-cycle.

## Troubleshooting

See the per-bot CLAUDE.md files. Common cases:

- **Bot silent after `/up`** → wrong `ALLOWED_TELEGRAM_USER_ID`. Both bots silently ignore unauthorized users.
- **Agent bot ignores my paste** → you must `/up` and pick a subdomain *first*. Pasting without a pending `/up` is silently ignored on purpose.
- **Picker/blob subdomain mismatch** → blob was generated for a different subdomain than you picked. Re-run `/up` on the Agent bot and pick the right one.
- **Blob says "unsupported blob version"** → the Infra bot was upgraded to a newer schema than the Agent bot. Update both.

# Remote Control

Browser-based remote desktop over WebRTC. A desktop agent streams its screen and receives mouse/keyboard input from any modern browser, with a signaling server handling auth and WebRTC handshake.

```
Browser (web/)  ──WS──►  Server (server/)  ──WS──►  Agent (agent/)
       │                                                    │
       └──────── WebRTC peer-to-peer (video + input) ──────┘
```

Once the WebRTC connection is established, video and input flow directly peer-to-peer. The server is only involved during signaling.

## Components

| Directory | Stack | Role |
| --- | --- | --- |
| [`agent/`](agent/README.md) | Python 3.9+, aiortc, mss, pynput | Captures screen, streams via WebRTC, injects input. Runs on the machine being controlled. |
| [`server/`](server/README.md) | Python 3.9+, FastAPI, uvicorn | JWT/Google OAuth auth, WebRTC signaling relay, rate limiting. |
| [`web/`](web/README.md) | React 19, TypeScript, Vite | Browser client. Authenticates, negotiates WebRTC, renders video, captures input via Pointer Lock. |

Each component has its own README with install/configuration details.

## Quick Start (local)

### 1. Server

```bash
cd server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
# listens on http://localhost:8000
```

### 2. Web client

```bash
cd web
npm install
npm run dev
# opens http://localhost:5173
```

### 3. Agent

ffmpeg@7 must be on PATH before installing Python deps (PyAV links against it).

```bash
# macOS:
brew install ffmpeg@7
export PKG_CONFIG_PATH="/opt/homebrew/opt/ffmpeg@7/lib/pkgconfig"

cd agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py --server ws://localhost:8000/ws/signaling --token "$AGENT_TOKEN"
```

On first run:
- **macOS** — grant Accessibility permission to the terminal for `pynput` input injection.
- **Linux** — add your user to the `input` group if input doesn't work.
- **Windows** — admin terminal may be needed for input injection.

Open the web client, sign in with Google, and select the agent to begin a session.

## Features

- Real-time screen streaming via WebRTC (low latency, peer-to-peer)
- Mouse and keyboard input injection with Pointer Lock capture in the browser
- JWT auth with password or Google OAuth (with domain/email allowlists)
- Per-IP rate limiting against brute-force login attempts
- Multi-monitor support and configurable FPS / resolution scaling
- Auto-reconnect on agent and browser sides
- Connection quality metrics (FPS, latency, jitter, packet loss, bitrate)

## Configuration

All configuration is via environment variables or CLI flags. See each component's README for the full list:

- Server: auth password, JWT secret, SSL, CORS, rate-limit thresholds, Google OAuth, WebSocket timeouts.
- Agent: signaling URL, password, agent ID, token, monitor, FPS, scale.
- Web (build-time): `VITE_API_URL`, `VITE_WS_URL`, `VITE_GOOGLE_CLIENT_ID`.

## Deployment

The [`deploy/`](deploy/) directory ships an end-to-end pipeline that provisions a DigitalOcean droplet, ships the `server/` and `web/` sources, runs them behind Caddy (TLS via Let's Encrypt), and points a DNS A-record at the new host. Two equivalent frontends are provided:

- `deploy/deploy.py` — Python (3.11+), the canonical implementation. Also importable as `rc_deploy` for embedding (e.g. a Telegram bot).
- `deploy/up.sh` / `deploy/down.sh` — bash equivalents.

### Setup

**1. Install local tools.** All scripts call out to these:

```bash
# macOS:
brew install doctl jq rsync
# (ssh and curl ship with the OS)

# Debian/Ubuntu:
sudo snap install doctl
sudo apt install jq rsync openssh-client curl
```

**2. Authenticate `doctl`.** Create a token at <https://cloud.digitalocean.com/account/api/tokens> with read+write scopes for droplets and domains, then:

```bash
doctl auth init       # paste the token when prompted
doctl account get     # sanity check
```

**3. Register an SSH key with DigitalOcean.** The droplet's `rc` user is provisioned with this key by `cloud-init.yaml`.

```bash
# Upload an existing public key:
doctl compute ssh-key import my-key --public-key-file ~/.ssh/id_ed25519.pub

# List keys to get the fingerprint for DO_SSH_KEY_FINGERPRINT:
doctl compute ssh-key list
```

**4. Point a domain at DigitalOcean DNS.** The domain must already be managed by DO (the scripts create/update an A-record under it, they do not register the domain itself).

```bash
doctl compute domain list
# If your domain isn't listed, add it and update its NS records at the registrar:
doctl compute domain create example.com
```

**5. Set up the `.env` file.**

```bash
cd deploy
cp .env.example .env
```

Required fields (the config loader rejects missing values and `CHANGE_ME*` placeholders):

| Var | How to obtain |
| --- | --- |
| `DO_API_TOKEN` | Step 2 above |
| `DO_REGION` / `DO_SIZE` / `DO_IMAGE` | Defaults in `.env.example` work; list options with `doctl compute region list`, `doctl compute size list`, `doctl compute image list-distribution` |
| `DO_SSH_KEY_FINGERPRINT` | `doctl compute ssh-key list` |
| `SSH_PRIVATE_KEY` | Local path to the matching private key (default `~/.ssh/id_ed25519`) |
| `DOMAIN` / `SUBDOMAIN` | The A-record will be `SUBDOMAIN.DOMAIN` |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `AGENT_TOKENS` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` — comma-separated list. Each agent registers with one of these via `--token`. |
| `GOOGLE_CLIENT_ID` | OAuth client ID from Google Cloud Console (see `GOOGLE_OAUTH.md` if present) |
| `GOOGLE_ALLOWED_EMAILS` / `GOOGLE_ALLOWED_DOMAINS` | Optional allowlists |

**6. (Python entrypoint only) install its deps.** Requires Python 3.11+.

```bash
python3.11 -m venv deploy/.venv
source deploy/.venv/bin/activate
pip install -r deploy/requirements.txt
```

The bash scripts (`up.sh` / `down.sh`) have no Python dependency and work out of the box once steps 1–5 are done.

### Bring the stack up

```bash
# Python:
python deploy/deploy.py up

# or bash:
./deploy/up.sh
```

This creates a droplet, writes `deploy/.state.json` (droplet id, IP, FQDN), upserts the `SUBDOMAIN.DOMAIN` A-record, waits for SSH and cloud-init, rsyncs `server/` + `web/` + `docker-compose.yml` + `Caddyfile`, renders a minimal `.env` on the droplet, and runs `docker compose up -d --build`. It finishes by polling `https://FQDN/api/health` until TLS is issued.

### Tear the stack down

```bash
python deploy/deploy.py down              # destroy droplet, keep DNS
python deploy/deploy.py down --clear-dns  # destroy droplet and delete A-record
# or: ./deploy/down.sh [--clear-dns]
```

This attempts a best-effort `docker compose down`, destroys the droplet tracked in `deploy/.state.json`, optionally removes the A-record, and clears the state file so `up` can run again.

### Notes

- `deploy/.state.json` is the single source of truth for "is a droplet running?". Delete it manually only if you know it's stale — otherwise `up` will refuse to create a second droplet.
- The droplet's `~/app/.env` is regenerated on every `up` from a subset of `deploy/.env` (auth/OAuth/session vars only). DigitalOcean/SSH vars are never shipped to the droplet.
- STUN-only — see the note below.

## Infra bot in Docker (deploy from Telegram)

The usual way to run the stack: the Infra bot (`bot/infra/`) runs in Docker on your PC and does `up`/`down` for you when you send `/up` and `/down` in Telegram. Tested on Windows + Docker Desktop with Git Bash. Full reference: [`bot/infra/RUN_DOCKER.md`](bot/infra/RUN_DOCKER.md).

**0. Things you need before you start (one-time):**

- Docker Desktop running (`docker compose version` works).
- A Telegram bot token from @BotFather. It must be a different bot from the Agent bot.
- Your numeric Telegram user id, from @userinfobot.
- A DigitalOcean API token with read+write access to droplets and domains.
- A domain whose DNS is hosted on DigitalOcean.
- A Google OAuth client ID.

**1. Create a deploy SSH key with no passphrase.** A key with a passphrase will not work: the bot has no terminal to type the passphrase into, so `/up` hangs waiting for SSH and then fails with a timeout.

```bash
ssh-keygen -t ed25519 -N "" -C rc-deploy -f ~/.ssh/id_ed25519_rc_deploy
doctl compute ssh-key import rc-deploy --public-key-file ~/.ssh/id_ed25519_rc_deploy.pub
ssh-keygen -l -E md5 -f ~/.ssh/id_ed25519_rc_deploy.pub   # fingerprint; drop the "MD5:" prefix
```

(Skip this step if `~/.ssh/id_ed25519_rc_deploy` already exists and `doctl compute ssh-key list` shows it.)

**2. Fill in `bot/infra/.env`.** This is the only env file the bot reads, so don't edit `deploy/.env` for this.

```bash
cd bot/infra
cp .env.example .env      # skip if .env already exists
```

| Var | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | the BotFather token |
| `ALLOWED_TELEGRAM_USER_ID` | your numeric Telegram id |
| `DO_API_TOKEN` | the DigitalOcean token |
| `DO_SSH_KEY_FINGERPRINT` | the fingerprint from step 1 |
| `DOMAIN` | e.g. `myvpnsrv1234.online` |
| `GOOGLE_CLIENT_ID` | the OAuth client ID |
| `GOOGLE_ALLOWED_EMAILS` | **your real Google address.** If you leave `you@example.com`, every sign-in gets "User not authorized"; `/up` now refuses to start with it. |

You also have to give the bot the SSH key. **On Windows**, mounting the key file does not work: inside the container the file belongs to root, so the bot can't read it. Pass the key inline instead:

```bash
echo "SSH_KEY_FILE=/run/secrets/ssh_key_unused" >> .env
echo "SSH_PRIVATE_KEY_B64=$(base64 -w0 ~/.ssh/id_ed25519_rc_deploy)" >> .env
```

On Linux you can set `SSH_KEY_HOST_PATH=/home/you/.ssh/id_ed25519_rc_deploy` instead.

**3. Build the image and start the bot** (from `bot/infra/`):

```bash
docker compose up -d --build --force-recreate
docker compose logs -f | grep -v api.telegram.org   # wait for "Infra bot starting", then Ctrl+C
```

**4. Use it from Telegram.**

- `/up` in the Infra bot, then pick a subdomain (`rc`…`rc3`). It takes a few minutes. When it's done, the bot replies with a credentials blob.
- Paste that blob into the Agent bot and `/up` there. Then open `https://<subdomain>.<DOMAIN>` and sign in with Google.
- To shut down: `/down` in the Agent bot first, then `/down` in the Infra bot. This deletes the droplet, which is what stops the billing.

**5. After `git pull` or any code change.** The image contains its own copy of `deploy/`, `server/` and `web/`, and a running droplet keeps the code it was deployed with. So:

1. `/down` (if a stack is up).
2. `docker compose up -d --build --force-recreate` in `bot/infra/`.
3. `/up`.

A plain `docker compose up -d` without `--build` keeps running the old code.

**6. When something goes wrong:**

| Symptom | Fix |
| --- | --- |
| Bot doesn't answer at all | Check `docker compose ps` and the logs. Usually a wrong token or user id, or the container is restarting in a loop because of `entrypoint: …` errors. |
| `/up` says "Deployment already in progress." | A previous deploy is still recorded. Run `/down`. If the droplet is already gone, see "Reset the state" in `RUN_DOCKER.md`. |
| `/up` times out waiting for SSH | The key has a passphrase, or the fingerprint doesn't match the key. Debug with `docker compose exec infra-bot ssh -v -i ~/.ssh/id_deploy rc@<ip>`. |
| "User not authorized" in the browser | Set `GOOGLE_ALLOWED_EMAILS` correctly, then do step 5. |

**Never** run `docker compose down -v` while a droplet is up. The `infra_state` volume holds the droplet id; if you wipe it, the bot can't delete the droplet and you have to delete it by hand in the DigitalOcean dashboard.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture overview for AI assistants (and humans skimming the repo)
- Per-component: [`agent/README.md`](agent/README.md), [`server/README.md`](server/README.md), [`web/README.md`](web/README.md)
- Per-component deep dives: `agent/CLAUDE.md`, `server/CLAUDE.md`, `web/CLAUDE.md`

## Notes

- STUN servers are hardcoded to Google's public STUN (`stun.l.google.com:19302`). No TURN is configured — strict NAT environments will need one added.
- The root `.gitignore` excludes `*.md` and `*.json` globally. If you want this README tracked, force-add it: `git add -f README.md`.

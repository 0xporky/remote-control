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

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture overview for AI assistants (and humans skimming the repo)
- Per-component: [`agent/README.md`](agent/README.md), [`server/README.md`](server/README.md), [`web/README.md`](web/README.md)
- Per-component deep dives: `agent/CLAUDE.md`, `server/CLAUDE.md`, `web/CLAUDE.md`

## Notes

- STUN servers are hardcoded to Google's public STUN (`stun.l.google.com:19302`). No TURN is configured — strict NAT environments will need one added.
- The root `.gitignore` excludes `*.md` and `*.json` globally. If you want this README tracked, force-add it: `git add -f README.md`.

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
python main.py --server ws://localhost:8000/ws/signaling --password admin
```

On first run:
- **macOS** — grant Accessibility permission to the terminal for `pynput` input injection.
- **Linux** — add your user to the `input` group if input doesn't work.
- **Windows** — admin terminal may be needed for input injection.

Open the web client, log in with the password (default `admin`), and select the agent to begin a session.

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

A deploy script is planned for a future iteration. The server ships a Dockerfile (`server/Dockerfile`) and the web client builds to a static `dist/` folder via `npm run build`.

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — architecture overview for AI assistants (and humans skimming the repo)
- Per-component: [`agent/README.md`](agent/README.md), [`server/README.md`](server/README.md), [`web/README.md`](web/README.md)
- Per-component deep dives: `agent/CLAUDE.md`, `server/CLAUDE.md`, `web/CLAUDE.md`

## Notes

- STUN servers are hardcoded to Google's public STUN (`stun.l.google.com:19302`). No TURN is configured — strict NAT environments will need one added.
- The root `.gitignore` excludes `*.md` and `*.json` globally. If you want this README tracked, force-add it: `git add -f README.md`.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

Three-component system for browser-based remote desktop via WebRTC:

- `agent/` — Python desktop agent. Captures the screen, streams video over WebRTC, and injects mouse/keyboard from the remote browser. Runs on the machine being controlled.
- `server/` — Python FastAPI signaling server. Handles JWT/Google OAuth, relays WebRTC SDP and ICE between agents and browser clients. Does **not** relay video or input — those are peer-to-peer.
- `web/` — React + TypeScript + Vite browser client. Authenticates against the server, negotiates WebRTC to an agent, displays video, captures input via Pointer Lock.

Each subdirectory has its own `CLAUDE.md` with detailed architecture, class responsibilities, message protocols, and debugging tips. **Read those first** before touching files in that component — they document non-obvious flows (offer/answer sequencing, session timeout logic, input event mapping) that are not obvious from the code alone.

Also see `AGENT_SET.md` (Windows agent install) and `DEPLOY.md` (DigitalOcean App Platform deployment).

## End-to-End Flow

```
Browser (web/)  ──WS──►  Server (server/)  ──WS──►  Agent (agent/)
       │                                                    │
       └──────── WebRTC peer-to-peer (video + input) ──────┘
```

The server is only involved during signaling. Once the WebRTC connection is up, video frames (agent → browser) and input events (browser → agent) go directly peer-to-peer. This means server load stays low regardless of stream volume, but also means ICE/STUN must succeed for the connection to work at all.

## Common Commands

### `web/` (from `web/`)

```bash
npm install         # install deps
npm run dev         # vite dev server with HMR
npm run build       # tsc -b && vite build → dist/
npm run lint        # eslint
npm run preview     # preview built dist
```

No test runner configured.

### `server/` (from `server/`)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py      # starts uvicorn on :8000 with auto-reload
```

No test suite. Smoke-test with `curl http://localhost:8000/api/health` and `wscat -c ws://localhost:8000/ws/signaling`.

### `agent/` (from `agent/`)

Requires **ffmpeg@7** on PATH before `pip install` (PyAV links against it). macOS: `brew install ffmpeg@7 && export PKG_CONFIG_PATH="/opt/homebrew/opt/ffmpeg@7/lib/pkgconfig"`.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py --server ws://localhost:8000/ws/signaling --password admin
```

CLI flags: `--server/-s`, `--password/-p`, `--agent-id/-i`, `--token/-t`, `--monitor/-m`, `--fps/-f`, `--scale`. Env vars: `SERVER_URL`, `AGENT_PASSWORD`, `AGENT_ID`, `AGENT_TOKEN`.

Platform notes: macOS needs Accessibility permission for `pynput` input injection; Linux may need the user in the `input` group; Windows may need admin terminal.

## Cross-Component Contracts

Changes to any of these touch all three components — update all of them together:

- **Signaling message schema** — Pydantic models in `server/messages.py` are the source of truth. `agent/signaling.py` and `web/src/services/signaling.ts` must match. Message types: `authenticate`, `authenticated`, `register`, `registered`, `list-agents`/`get-agents`, `agent-list`/`agents-list`, `offer`, `answer`, `ice-candidate`, `error`.
- **Input event schema** — browser → agent over WebRTC data channel `"input"`. Types: `mousemove` (dx/dy, Pointer Lock relative), `mousedown`/`mouseup` (button 0/1/2), `wheel` (deltaX/deltaY), `keydown`/`keyup` (key + code). Defined in `web/src/types/index.ts`, handled in `agent/input_handler.py`.
- **Auth** — server issues JWT via `SECRET_KEY`; both password and Google OAuth paths produce the same token. Browser sends it in the `authenticate` WS message. Agents register with `AUTH_PASSWORD` plus optional `AGENT_TOKEN` (required if `AGENT_TOKEN_REQUIRED=true`).
- **STUN servers** — hardcoded as `stun.l.google.com:19302` and `stun1.l.google.com:19302` in both `agent/webrtc_client.py` and `web/src/services/webrtc.ts`. No TURN configured; behind strict NAT, ICE will fail.

## Deployment Notes (see DEPLOY.md)

- Target platform is DigitalOcean App Platform: `server` as a Web Service (Dockerfile, port 8000), `web` as a Static Site (`npm ci && npm run build`, output `dist/`).
- Platform terminates TLS at the load balancer → keep `SSL_ENABLED=false` on the server.
- App Platform idle-closes connections at 60s; server sends WS pings every 30s (`WS_PING_INTERVAL_SECONDS`) to stay alive — don't raise this above ~50s.
- Build-time env vars for `web`: `VITE_API_URL`, `VITE_WS_URL`, `VITE_GOOGLE_CLIENT_ID`. These are baked into the bundle, so redeploy `web` after changing.

## Repo Hygiene

The root `.gitignore` excludes `*.md` and `*.json` globally. This is intentional — the repo currently holds operational docs (`DEPLOY.md`, `AGENT_SET.md`, `env_variables.md`, `GOOGLE_OAUTH.md`) and an OAuth client secret JSON that should not be committed. If you add a file that needs tracking (e.g. `package.json`, `tsconfig.json`, a `README.md`), force-add it with `git add -f <path>` or add a negated pattern to `.gitignore`.

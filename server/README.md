# Remote Control Server

A FastAPI-based signaling server for WebRTC remote desktop connections. Handles client/agent authentication, WebSocket signaling for WebRTC handshake, and serves the web client.

## Features

- JWT-based authentication with configurable expiration
- Google OAuth support with domain/email allowlists
- WebRTC signaling relay for peer-to-peer connections
- Rate limiting protection against brute force attacks
- SSL/TLS support for production deployments
- Configurable CORS for cross-origin requests
- WebSocket session timeout management
- In-memory connection management (no database required)
- Static file serving for SPA web client

## Prerequisites

- Python 3.9+
- pip

## Installation

### 1. Create Virtual Environment

```bash
cd server
python -m venv venv

# Activate:
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

All configuration is done via environment variables. Create a `.env` file or export variables directly.

### Server Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |

### SSL/HTTPS Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SSL_ENABLED` | Enable HTTPS | `false` |
| `SSL_KEYFILE` | Path to SSL private key | None |
| `SSL_CERTFILE` | Path to SSL certificate | None |

### Security Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (change in production!) | `change-this-...` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime | `60` |

### Agent Authorization

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_TOKENS` | Comma-separated list of valid agent tokens. **Required** — empty list rejects all agents. | None |

### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` | Max login attempts before lockout | `5` |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | Time window for attempt counting | `60` |
| `RATE_LIMIT_LOGIN_LOCKOUT_SECONDS` | Lockout duration after max attempts | `300` |

### WebSocket Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `WS_SESSION_TIMEOUT_SECONDS` | Idle timeout for WebSocket connections | `3600` |
| `WS_PING_INTERVAL_SECONDS` | Ping interval for keepalive | `30` |
| `WS_PING_TIMEOUT_SECONDS` | Ping response timeout | `10` |

### CORS Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ORIGINS` | Allowed origins (comma-separated or `*`) | `*` |

### Google OAuth Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | None |
| `GOOGLE_ALLOWED_DOMAINS` | Allowed email domains (comma-separated) | None |
| `GOOGLE_ALLOWED_EMAILS` | Allowed email addresses (comma-separated) | None |

### Static Files

| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_CLIENT_PATH` | Path to web client build directory | `../web/dist` |

## Usage

### Development

```bash
python main.py
```

Server starts at `http://localhost:8000` with auto-reload enabled.

### Production

```bash
# Set secure configuration
export SECRET_KEY="your-secure-random-key-at-least-32-chars"
export AGENT_TOKENS="token1,token2,token3"
export SSL_ENABLED=true
export SSL_KEYFILE=/path/to/privkey.pem
export SSL_CERTFILE=/path/to/fullchain.pem

python main.py
```

### Docker

```bash
# Build
docker build -t remote-control-server .

# Run with environment variables
docker run -p 8000:8000 \
  -e SECRET_KEY="your-secure-key" \
  -e AGENT_TOKENS="token1,token2" \
  remote-control-server

# Run with .env file
docker run -p 8000:8000 --env-file .env remote-control-server
```

### Example .env File

```env
# Security (CHANGE THESE IN PRODUCTION)
SECRET_KEY=your-very-long-and-secure-random-string-here

# Required: Agent authorization tokens (comma-separated)
AGENT_TOKENS=token1,token2,token3

# Optional: Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_ALLOWED_DOMAINS=yourcompany.com

# Optional: SSL
SSL_ENABLED=true
SSL_KEYFILE=/etc/ssl/private/server.key
SSL_CERTFILE=/etc/ssl/certs/server.crt
```

## API Reference

### REST Endpoints

#### Health Check
```
GET /api/health
```
Returns `{"status": "ok"}` if server is running.

#### Google OAuth Login
```
POST /api/auth/google
Content-Type: application/json

{"credential": "google-id-token"}
```
Returns JWT token on success.

#### Generate Agent Token
```
GET /api/generate-agent-token
```
Returns a secure random token for agent authorization:
```json
{"token": "abc123..."}
```

### WebSocket Endpoint

```
WS /ws/signaling
```

#### Message Types

**Client Authentication:**
```json
{"type": "authenticate", "token": "jwt-token"}
```

**Agent Registration:**
```json
{"type": "register", "agent_id": "my-agent", "token": "agent-token"}
```

**Get Available Agents:**
```json
{"type": "get-agents"}
```

**WebRTC Signaling:**
```json
{"type": "offer", "sdp": "...", "target": "agent-id"}
{"type": "answer", "sdp": "...", "target": "client-connection-id"}
{"type": "ice-candidate", "candidate": {...}, "target": "connection-id"}
```

## Troubleshooting

### Connection Issues

- Verify server URL is correct (ws:// for HTTP, wss:// for HTTPS)
- Check firewall allows connections on configured port
- For SSL, ensure certificates are valid and paths are correct

### Authentication Failures

- Check JWT `SECRET_KEY` is consistent across restarts
- For Google OAuth, verify `GOOGLE_CLIENT_ID` matches frontend

### WebSocket Disconnects

- Check `WS_SESSION_TIMEOUT_SECONDS` (default 1 hour)
- Verify client is sending messages to keep connection alive
- Check network stability and proxy timeout settings

### Rate Limiting

- After 5 failed attempts, IP is locked out for 5 minutes
- Check `RATE_LIMIT_*` settings to adjust thresholds
- Rate limit resets on successful login

### Agent Registration Fails

- Agent must send a `--token` matching one of the entries in `AGENT_TOKENS`
- If `AGENT_TOKENS` is empty on the server, all registrations are rejected (check startup logs for the warning)

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.104.0 | Web framework |
| uvicorn | >=0.24.0 | ASGI server |
| websockets | >=12.0 | WebSocket support |
| python-jose | >=3.3.0 | JWT token handling |
| google-auth | >=2.23.0 | Google OAuth verification |
| python-multipart | >=0.0.6 | Form data parsing |

## License

See the main project repository for license information.

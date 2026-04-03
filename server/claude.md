# Server Development Guide

Technical reference for developing and debugging the Remote Control Server.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              main.py                                     │
│                           FastAPI App                                    │
│  ┌────────────┬──────────────┬──────────────┬────────────────────────┐  │
│  │  REST API  │   Middleware │   Lifespan   │    Static Files        │  │
│  │ /api/*     │   CORS       │   startup    │    /assets, SPA        │  │
│  └─────┬──────┴──────────────┴──────────────┴────────────────────────┘  │
│        │                                                                 │
│  ┌─────┴──────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │  auth.py   │  │ signaling.py │  │ messages.py │  │rate_limiter.py │  │
│  │ JWT/OAuth  │  │ Conn Manager │  │  Pydantic   │  │ Brute Force    │  │
│  └────────────┘  └──────┬───────┘  └─────────────┘  └────────────────┘  │
└─────────────────────────┼───────────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │  routes/websocket.py  │
              │   WebSocket Handler   │
              │   SessionManager      │
              └───────────────────────┘
```

## File Descriptions

| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `main.py` | ~150 | FastAPI application, REST endpoints, static files | `app` |
| `auth.py` | ~180 | JWT tokens, password auth, Google OAuth | `create_access_token()`, `verify_token()`, `verify_google_token()` |
| `config.py` | ~80 | Environment variable configuration | All `*` constants |
| `signaling.py` | ~100 | WebSocket connection management | `ConnectionManager`, `manager` |
| `messages.py` | ~200 | Pydantic message validation models | `validate_message()`, `validate_input_event()` |
| `rate_limiter.py` | ~100 | Rate limiting for brute force protection | `RateLimiter`, `login_rate_limiter` |
| `routes/websocket.py` | ~250 | WebSocket endpoint and session management | `router`, `SessionManager` |

## Key Classes

### ConnectionManager (signaling.py)

Manages all active WebSocket connections and agent registrations.

```python
class ConnectionManager:
    _connections: dict[str, Connection]  # connection_id -> Connection
    _agents: dict[str, str]              # agent_id -> connection_id
    _lock: asyncio.Lock                   # Thread-safety

    async def connect(websocket, connection_id)      # Accept and register
    async def disconnect(connection_id)              # Remove and cleanup
    async def register_agent(connection_id, agent_id)  # Mark as agent
    def get_agent_list() -> list[str]                # List agent IDs
    async def send_to_agent(agent_id, message)       # Send JSON to agent
    async def relay_message(from_id, target_id, msg) # Relay with "from" field
```

**Thread Safety:** All mutations use `async with self._lock` to prevent race conditions.

**Agent Lookup:** Messages to agents first check `_agents` dict, then fall back to `_connections`.

### SessionManager (routes/websocket.py)

Tracks per-connection state and manages session timeouts.

```python
class SessionManager:
    websocket: WebSocket
    connection_id: str
    authenticated: bool = False
    is_agent: bool = False
    created_at: datetime
    last_activity: datetime
    _timeout_task: Optional[asyncio.Task]

    def update_activity()                    # Update last_activity timestamp
    def is_expired() -> bool                 # Check if idle > timeout
    async def start_timeout_monitor(callback)  # Background timeout checker
    async def stop_timeout_monitor()         # Cancel timeout task
```

**Timeout Behavior:** Every 30 seconds, checks if idle time exceeds `WS_SESSION_TIMEOUT_SECONDS`. Sends error and closes connection on timeout.

### RateLimiter (rate_limiter.py)

Per-IP rate limiting with configurable windows and lockouts.

```python
class RateLimiter:
    _attempts: dict[str, list[float]]  # IP -> list of timestamps
    _lockouts: dict[str, float]        # IP -> lockout end time

    async def is_allowed(client_ip) -> tuple[bool, str]  # Check if allowed
    async def record_attempt(client_ip, success: bool)   # Track attempt
    async def cleanup()                                   # Remove expired
```

**Lockout Logic:**
1. Track timestamps of failed attempts per IP
2. Clean attempts older than window
3. If attempts >= max, set lockout time
4. During lockout, reject all requests
5. Successful login clears attempt history

### Connection (signaling.py)

Dataclass representing a single WebSocket connection.

```python
@dataclass
class Connection:
    websocket: WebSocket
    connection_id: str
    is_agent: bool = False
    agent_id: Optional[str] = None
```

## Authentication Flows

### Password Authentication

```
Client                          Server
   │                               │
   │ POST /api/auth/login          │
   │ {"password": "secret"}        │
   │──────────────────────────────>│
   │                               │ 1. Check rate limit (IP)
   │                               │ 2. Verify password == AUTH_PASSWORD
   │                               │ 3. Record attempt (success/fail)
   │                               │ 4. Generate JWT token
   │ {"access_token": "eyJ..."}    │
   │<──────────────────────────────│
```

### Google OAuth Authentication

```
Client                          Server                         Google
   │                               │                               │
   │ (Google Sign-In popup)        │                               │
   │<─────────────────────────────────────────────────────────────>│
   │ credential (ID token)         │                               │
   │                               │                               │
   │ POST /api/auth/google         │                               │
   │ {"credential": "eyJ..."}      │                               │
   │──────────────────────────────>│                               │
   │                               │ 1. Check rate limit           │
   │                               │ 2. Verify token with Google ──│──>
   │                               │ 3. Verify issuer = google.com │
   │                               │ 4. Check email_verified       │
   │                               │ 5. Check allowlist            │
   │                               │ 6. Generate JWT               │
   │ {"access_token": "eyJ..."}    │                               │
   │<──────────────────────────────│                               │
```

**Allowlist Logic:**
- If both `GOOGLE_ALLOWED_DOMAINS` and `GOOGLE_ALLOWED_EMAILS` are empty: allow all
- If domains set: email domain must match one
- If emails set: exact email must be in list

### WebSocket Authentication (Clients)

```
Client                          Server
   │                               │
   │ WS /ws/signaling              │
   │──────────────────────────────>│
   │ {"type": "connected",         │
   │  "connection_id": "uuid"}     │
   │<──────────────────────────────│
   │                               │
   │ {"type": "authenticate",      │
   │  "token": "eyJ..."}           │
   │──────────────────────────────>│
   │                               │ verify_token()
   │ {"type": "authenticated"}     │
   │<──────────────────────────────│
```

### WebSocket Registration (Agents)

```
Agent                           Server
   │                               │
   │ WS /ws/signaling              │
   │──────────────────────────────>│
   │ {"type": "connected",         │
   │  "connection_id": "uuid"}     │
   │<──────────────────────────────│
   │                               │
   │ {"type": "register",          │
   │  "agent_id": "workstation-1", │
   │  "password": "secret",        │
   │  "token": "agent-token"}      │
   │──────────────────────────────>│
   │                               │ 1. Verify password
   │                               │ 2. Verify token (if required)
   │                               │ 3. Register in ConnectionManager
   │ {"type": "registered"}        │
   │<──────────────────────────────│
```

## WebSocket Protocol

### Message Types

| Type | Direction | Auth Required | Purpose |
|------|-----------|---------------|---------|
| `connected` | S→C | No | Initial connection confirmation |
| `authenticate` | C→S | No | Client JWT authentication |
| `authenticated` | S→C | No | Auth success confirmation |
| `register` | A→S | No | Agent registration |
| `registered` | S→A | No | Registration success |
| `get-agents` | C→S | Yes | Request agent list |
| `agents-list` | S→C | Yes | Agent list response |
| `offer` | C→S | Yes | WebRTC SDP offer |
| `answer` | A→S | Yes | WebRTC SDP answer |
| `ice-candidate` | Both | Yes | ICE candidate |
| `error` | S→Both | No | Error message |

### Connection Lifecycle

```
1. CONNECT
   └─> Generate connection_id (UUID)
   └─> Accept WebSocket
   └─> Register in ConnectionManager
   └─> Send "connected" message
   └─> Start timeout monitor

2. AUTHENTICATE/REGISTER
   └─> Validate credentials
   └─> Mark session authenticated
   └─> (Agents) Register agent_id

3. MESSAGE LOOP
   └─> Receive JSON message
   └─> Validate with Pydantic
   └─> Update activity timestamp
   └─> Handle based on type
   └─> Relay to target if applicable

4. DISCONNECT
   └─> Stop timeout monitor
   └─> Remove from ConnectionManager
   └─> (Agents) Unregister agent_id
   └─> Log disconnection
```

## Data Flow

### WebRTC Signaling Flow

```
Browser Client              Signaling Server              Desktop Agent
      │                            │                            │
      │ {"type": "offer",          │                            │
      │  "sdp": "...",             │                            │
      │  "target": "agent-1"}      │                            │
      │───────────────────────────>│                            │
      │                            │ {"type": "offer",          │
      │                            │  "sdp": "...",             │
      │                            │  "from": "client-uuid"}    │
      │                            │───────────────────────────>│
      │                            │                            │
      │                            │ {"type": "answer",         │
      │                            │  "sdp": "...",             │
      │                            │  "target": "client-uuid"}  │
      │                            │<───────────────────────────│
      │ {"type": "answer",         │                            │
      │  "sdp": "...",             │                            │
      │  "from": "agent-1"}        │                            │
      │<───────────────────────────│                            │
      │                            │                            │
      │ {"type": "ice-candidate",  │                            │
      │  "candidate": {...},       │                            │
      │  "target": "agent-1"}      │                            │
      │<─────────────────────────────────────────────────────────>│
      │        (bidirectional ICE candidate exchange)           │
      │                            │                            │
      │═══════════════════════════════════════════════════════════│
      │        WebRTC peer-to-peer connection established       │
```

### Input Event Flow (after WebRTC)

```
Browser → WebRTC Data Channel → Agent → pynput → OS
```

(Note: Input events go directly peer-to-peer, not through signaling server)

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | >=0.104.0 | Async web framework |
| `uvicorn[standard]` | >=0.24.0 | ASGI server with WebSocket support |
| `websockets` | >=12.0 | WebSocket protocol implementation |
| `python-jose[cryptography]` | >=3.3.0 | JWT token creation/verification |
| `passlib[bcrypt]` | >=1.7.4 | Secure password hashing |
| `python-multipart` | >=0.0.6 | Multipart form data parsing |
| `google-auth` | >=2.23.0 | Google ID token verification |

## Debugging

### Enable Logging

Add to `main.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific modules:
logging.getLogger("routes.websocket").setLevel(logging.DEBUG)
logging.getLogger("signaling").setLevel(logging.DEBUG)
```

### Key Log Points

| Module | What to Log |
|--------|-------------|
| `main.py` | Startup config, endpoint hits |
| `auth.py` | Token creation/verification, auth failures |
| `signaling.py` | Connection/disconnection, agent registration |
| `routes/websocket.py` | Message types, relay operations |
| `rate_limiter.py` | Lockouts, attempt counts |

### Common Issues

**1. JWT Decode Errors**
```
jose.exceptions.JWTError: Signature verification failed
```
- Check `SECRET_KEY` is consistent between token creation and verification
- Ensure token hasn't expired (check `ACCESS_TOKEN_EXPIRE_MINUTES`)

**2. WebSocket Disconnects**
```
websockets.exceptions.ConnectionClosed
```
- Check `WS_SESSION_TIMEOUT_SECONDS` (default 3600s = 1 hour)
- Client may need to send periodic messages
- Check proxy/load balancer timeout settings

**3. Rate Limited**
```
{"error": "Too many attempts. Try again in X seconds"}
```
- Wait for lockout period (default 300s)
- Check `RATE_LIMIT_LOGIN_*` configuration
- Rate limit applies per IP address

**4. Google OAuth Fails**
```
{"error": "Invalid Google token"}
```
- Verify `GOOGLE_CLIENT_ID` matches frontend
- Check token is fresh (Google tokens expire)
- Ensure clock sync between server and client

**5. Agent Registration Fails**
```
{"type": "error", "message": "Invalid agent token"}
```
- If `AGENT_TOKEN_REQUIRED=true`, token must be provided
- Token must be in `AGENT_TOKENS` list
- Password must match `AUTH_PASSWORD`

### Testing Individual Components

**Test REST Authentication:**
```bash
# Health check
curl http://localhost:8000/api/health

# Password login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin"}'

# Generate agent token
curl http://localhost:8000/api/generate-agent-token
```

**Test WebSocket with wscat:**
```bash
# Install: npm install -g wscat
wscat -c ws://localhost:8000/ws/signaling

# Then send messages:
> {"type": "authenticate", "token": "your-jwt-token"}
> {"type": "get-agents"}
```

**Test Rate Limiter:**
```python
import asyncio
from rate_limiter import login_rate_limiter

async def test():
    # Simulate failed attempts
    for i in range(6):
        allowed, msg = await login_rate_limiter.is_allowed("192.168.1.1")
        print(f"Attempt {i+1}: allowed={allowed}, msg={msg}")
        await login_rate_limiter.record_attempt("192.168.1.1", success=False)

asyncio.run(test())
```

## Configuration Reference

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | str | `0.0.0.0` | Server bind address |
| `PORT` | int | `8000` | Server port |
| `SSL_ENABLED` | bool | `false` | Enable HTTPS |
| `SSL_KEYFILE` | str | None | Path to SSL private key |
| `SSL_CERTFILE` | str | None | Path to SSL certificate |
| `SECRET_KEY` | str | `change-this...` | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `60` | JWT lifetime |
| `AUTH_PASSWORD` | str | `admin` | Client authentication password |
| `AGENT_TOKENS` | str | None | Comma-separated agent tokens |
| `AGENT_TOKEN_REQUIRED` | bool | `false` | Require agent token |
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` | int | `5` | Max login attempts |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | int | `60` | Attempt window |
| `RATE_LIMIT_LOGIN_LOCKOUT_SECONDS` | int | `300` | Lockout duration |
| `WS_SESSION_TIMEOUT_SECONDS` | int | `3600` | WebSocket idle timeout |
| `WS_PING_INTERVAL_SECONDS` | int | `30` | Ping interval |
| `WS_PING_TIMEOUT_SECONDS` | int | `10` | Ping timeout |
| `CORS_ORIGINS` | str | `*` | Allowed CORS origins |
| `GOOGLE_CLIENT_ID` | str | None | Google OAuth client ID |
| `GOOGLE_ALLOWED_DOMAINS` | str | None | Allowed email domains |
| `GOOGLE_ALLOWED_EMAILS` | str | None | Allowed email addresses |
| `WEB_CLIENT_PATH` | str | `../web/dist` | Static files path |

## Extending the Server

### Adding a New REST Endpoint

```python
# In main.py
@app.post("/api/my-endpoint")
async def my_endpoint(
    request: MyRequest,
    current_user: TokenData = Depends(get_current_user)  # Requires auth
):
    # Implementation
    return {"result": "success"}
```

### Adding a New WebSocket Message Type

1. Add Pydantic model in `messages.py`:
```python
class MyMessage(BaseModel):
    type: Literal["my-type"]
    data: str = Field(max_length=1000)
```

2. Add to discriminator in `validate_message()`:
```python
if msg_type == "my-type":
    return True, MyMessage(**data), None
```

3. Handle in `routes/websocket.py`:
```python
elif msg_type == "my-type":
    # Handle message
    await manager.send_to_connection(connection_id, {"type": "my-response"})
```

### Adding Custom Rate Limiting

```python
from rate_limiter import RateLimiter, RateLimitConfig

# Create custom limiter
api_rate_limiter = RateLimiter(RateLimitConfig(
    max_attempts=100,
    window_seconds=60,
    lockout_seconds=60
))

# Use in endpoint
@app.get("/api/limited")
async def limited_endpoint(request: Request):
    client_ip = get_client_ip(request)
    allowed, message = await api_rate_limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=message)
    await api_rate_limiter.record_attempt(client_ip, success=True)
    return {"status": "ok"}
```

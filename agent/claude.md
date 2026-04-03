# Agent Development Guide

Technical reference for developing and debugging the Remote Control Agent.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                         Agent class                              │
│  ┌──────────────┬───────────────┬───────────────┬────────────┐  │
│  │ SignalingCl. │ ScreenCapture │ WebRTCClient  │InputHandler│  │
│  │ (signaling)  │ (screen_cap)  │ (webrtc_cli)  │(input_hdlr)│  │
│  └──────┬───────┴───────┬───────┴───────┬───────┴─────┬──────┘  │
└─────────┼───────────────┼───────────────┼─────────────┼─────────┘
          │               │               │             │
          ▼               ▼               ▼             ▼
    ┌──────────┐   ┌───────────┐   ┌───────────┐  ┌──────────┐
    │WebSocket │   │    mss    │   │  aiortc   │  │  pynput  │
    │(server)  │   │ (screen)  │   │ (WebRTC)  │  │ (OS I/O) │
    └──────────┘   └───────────┘   └───────────┘  └──────────┘
```

## File Descriptions

| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `main.py` | Entry point | Application orchestration, signal handling | `Agent`, `main()` |
| `config.py` | ~100 | CLI argument parsing, environment variables | `Config` |
| `signaling.py` | ~150 | WebSocket connection to signaling server | `SignalingClient` |
| `webrtc_client.py` | ~200 | WebRTC peer connection management | `WebRTCClient`, `ScreenTrack` |
| `screen_capture.py` | ~120 | Screen capture with mss library | `ScreenCapture` |
| `input_handler.py` | ~180 | Mouse/keyboard injection via pynput | `InputHandler` |

## Key Classes

### Agent (main.py)

Main orchestrator that wires all components together.

```python
class Agent:
    def __init__(self, config: Config):
        self.signaling = SignalingClient(config)
        self.screen_capture = ScreenCapture(config.monitor, config.scale, config.fps)
        self.webrtc = WebRTCClient(self.screen_capture, ...)
        self.input_handler = InputHandler()
```

**Lifecycle:**
1. `__init__` - Creates all component instances
2. `run()` - Starts signaling client, enters main loop
3. Signal handlers for SIGINT/SIGTERM trigger `shutdown()`
4. `shutdown()` - Closes WebRTC connections, stops signaling

### SignalingClient (signaling.py)

WebSocket client for communication with signaling server.

**Message Types Handled:**
- `connected` - Server confirms connection, provides `connection_id`
- `registered` - Server confirms agent registration
- `offer` - Incoming WebRTC SDP offer from browser client
- `ice-candidate` - Incoming ICE candidate from client
- `error` - Server error message

**Key Methods:**
```python
await client.connect()           # Establish WebSocket connection
await client.register()          # Send registration with credentials
await client.send_answer(target, sdp)  # Send SDP answer to client
await client.send_ice_candidate(target, candidate)
client.on_offer(handler)         # Register callback for offers
client.on_ice_candidate(handler) # Register callback for ICE
```

**Reconnection:** Automatic with 5-second delay, unlimited attempts.

### WebRTCClient (webrtc_client.py)

Manages WebRTC peer connections and video streaming.

**Offer-Answer Flow:**
```
Browser creates offer → signaling server → agent.handle_offer()
                                              ↓
                    Creates RTCPeerConnection with STUN servers
                                              ↓
                    Adds ScreenTrack for video
                                              ↓
                    Creates answer → signaling server → browser
                                              ↓
                    ICE candidates exchanged bidirectionally
                                              ↓
                    Connection established, video streaming begins
```

**STUN Servers:**
- `stun:stun.l.google.com:19302`
- `stun:stun1.l.google.com:19302`

**Multi-client:** Supports multiple simultaneous browser connections via `peers` dict.

### ScreenTrack (webrtc_client.py)

Custom `aiortc.VideoStreamTrack` subclass that provides video frames.

```python
class ScreenTrack(VideoStreamTrack):
    async def recv(self) -> VideoFrame:
        # 1. Get timestamp for frame pacing
        pts, time_base = await self.next_timestamp()
        # 2. Capture screen frame via ScreenCapture
        image = self.screen_capture.capture_frame()
        # 3. Convert PIL Image to numpy array (RGB)
        frame_array = np.array(image)
        # 4. Create VideoFrame for WebRTC
        frame = VideoFrame.from_ndarray(frame_array, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame
```

### ScreenCapture (screen_capture.py)

Efficient screen capture using mss library.

**Capture Pipeline:**
```
mss.grab(monitor) → Screenshot (BGRA bytes)
        ↓
Image.frombytes() → PIL Image
        ↓
Convert BGRA → RGB
        ↓
Optional scaling (LANCZOS resampling)
        ↓
Return PIL Image
```

**Frame Pacing:**
```python
frame_interval = 1.0 / fps  # e.g., 33.3ms for 30 FPS
# After capture:
sleep_time = max(0, frame_interval - elapsed)
await asyncio.sleep(sleep_time)
```

**Monitor Indices:**
- `0` - All monitors combined
- `1` - Primary monitor (default)
- `2+` - Secondary monitors

### InputHandler (input_handler.py)

Injects mouse and keyboard input via pynput.

**Supported Events:**

| Type | Fields | Action |
|------|--------|--------|
| `mousemove` | `dx`, `dy` | Relative mouse movement |
| `mousedown` | `button` (0/1/2) | Press left/middle/right |
| `mouseup` | `button` | Release button |
| `wheel` | `deltaX`, `deltaY` | Scroll (normalized to clicks) |
| `keydown` | `key`, `code` | Press key |
| `keyup` | `key`, `code` | Release key |

**Key Mapping:** Browser key codes → pynput Key objects

Special keys supported: Shift, Control, Alt, Meta, Arrow keys, F1-F12, Enter, Tab, Escape, Backspace, Delete, Home, End, PageUp, PageDown, Insert, CapsLock, NumLock, ScrollLock, Pause, PrintScreen.

## Data Flow

### Connection Sequence

```
1. Agent starts
       ↓
2. SignalingClient.connect() → WebSocket to server
       ↓
3. Server sends: {"type": "connected", "connection_id": "..."}
       ↓
4. SignalingClient.register() → {"type": "register", "agent_id": "...", "password": "..."}
       ↓
5. Server sends: {"type": "registered"}
       ↓
6. SignalingClient.listen() → Wait for offers/ICE candidates
       ↓
7. Browser connects, sends offer via signaling
       ↓
8. WebRTCClient.handle_offer() → Create peer connection, send answer
       ↓
9. ICE candidates exchanged
       ↓
10. WebRTC connected, video streaming begins
```

### Input Event Flow

```
Browser captures mouse/keyboard
        ↓
Sends JSON via WebRTC data channel
        ↓
WebRTCClient._handle_data_message()
        ↓
Calls input_handler callback
        ↓
InputHandler.handle_input(event)
        ↓
pynput Mouse/Keyboard Controller
        ↓
Operating system input injection
```

## Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `aiortc` | WebRTC implementation | Requires ffmpeg for video encoding |
| `mss` | Screen capture | Fast, cross-platform, no external deps |
| `pynput` | Input injection | May need OS permissions |
| `websockets` | WebSocket client | Async, used for signaling |
| `av` | Audio/video processing | aiortc dependency, needs ffmpeg |
| `Pillow` | Image processing | Format conversion, scaling |
| `numpy` | Array operations | Frame handling, conversions |
| `aiohttp` | Async HTTP | Dependency for some operations |

## Debugging

### Enable Logging

Add to `main.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Or set environment variable:
```bash
export PYTHONVERBOSE=1
```

### Key Log Points

| Module | What to look for |
|--------|------------------|
| `signaling.py` | Connection status, message send/receive |
| `webrtc_client.py` | Peer connection state changes, ICE status |
| `screen_capture.py` | FPS achieved, capture errors |
| `input_handler.py` | Input events received, injection errors |

### Common Issues

**1. ffmpeg not found**
```
Error: No module named 'av'
```
Solution: Install ffmpeg@7 and set PKG_CONFIG_PATH before pip install.

**2. No video streaming**
- Check `ScreenCapture.capture_frame()` returns valid image
- Verify monitor index exists
- Check WebRTC connection state is "connected"

**3. No input**
- Verify data channel is open in `WebRTCClient`
- Check `InputHandler.enabled` is True
- OS permissions: accessibility (macOS), input group (Linux)

**4. Connection fails**
- Check server URL (ws:// vs wss://)
- Verify credentials match server config
- Check firewall allows WebSocket connections

**5. ICE connection fails**
- STUN servers reachable? Try `nc -vz stun.l.google.com 19302`
- Firewall blocking UDP?
- Consider adding TURN server for strict NAT

### Testing Components Individually

**Test screen capture:**
```python
from screen_capture import ScreenCapture
sc = ScreenCapture(monitor=1, scale=1.0, fps=30)
image = sc.capture_frame()
image.save("test_capture.png")
print(sc.get_stats())
```

**Test input handler:**
```python
from input_handler import InputHandler
ih = InputHandler()
ih.handle_input("test", {"type": "mousemove", "dx": 100, "dy": 0})
ih.handle_input("test", {"type": "keydown", "key": "a"})
ih.handle_input("test", {"type": "keyup", "key": "a"})
```

**Test signaling connection:**
```python
import asyncio
from signaling import SignalingClient
from config import Config

async def test():
    config = Config(server_url="ws://localhost:8000/ws/signaling", password="admin")
    client = SignalingClient(config)
    await client.connect()
    await client.register()
    print("Connected and registered!")

asyncio.run(test())
```

## Configuration Reference

### Config Class Properties

| Property | Type | Default | Source |
|----------|------|---------|--------|
| `server_url` | str | `ws://localhost:8000/ws/signaling` | `--server` / `SERVER_URL` |
| `password` | str | `admin` | `--password` / `AGENT_PASSWORD` |
| `agent_id` | str | hostname | `--agent-id` / `AGENT_ID` |
| `agent_token` | Optional[str] | None | `--token` / `AGENT_TOKEN` |
| `monitor` | int | 1 | `--monitor` |
| `fps` | int | 30 | `--fps` |
| `scale` | float | 1.0 | `--scale` |

### Reconnection Constants (config.py)

| Constant | Value | Description |
|----------|-------|-------------|
| `RECONNECT_DELAY` | 5 | Seconds between reconnection attempts |
| `MAX_RECONNECT_ATTEMPTS` | 0 | 0 = unlimited attempts |

## Extending the Agent

### Adding a New Input Type

1. Define message format in browser client
2. Add handler in `InputHandler.handle_input()`:
```python
def handle_input(self, client_id: str, event: dict):
    event_type = event.get("type")
    if event_type == "my_new_type":
        self._handle_my_new_type(event)
```

### Adding Telemetry

Hook into `ScreenCapture.get_stats()` and `WebRTCClient.get_connection_stats()`:
```python
stats = {
    "capture": self.screen_capture.get_stats(),
    "connections": self.webrtc.get_connection_stats(),
}
```

### Custom Video Processing

Modify `ScreenTrack.recv()` to add filters, overlays, or transformations before encoding:
```python
async def recv(self):
    image = self.screen_capture.capture_frame()
    # Add custom processing here
    image = apply_filter(image)
    frame_array = np.array(image)
    ...
```

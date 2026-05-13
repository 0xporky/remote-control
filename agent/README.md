# Remote Control Agent

A Python application that runs on the target machine, captures the screen in real-time, streams it via WebRTC, and injects mouse/keyboard input from a remote browser.

## Features

- Real-time screen capture and streaming via WebRTC
- Mouse and keyboard input injection
- Peer-to-peer connection (low latency)
- Auto-reconnection with exponential backoff
- Multi-monitor support
- Configurable FPS and resolution scaling

## Prerequisites

- Python 3.9+
- ffmpeg@7 (required for PyAV/aiortc video encoding)
- A running signaling server (see `server/` directory)

## Installation

### 1. Install ffmpeg@7

**macOS (Homebrew):**
```bash
brew install ffmpeg@7
export PKG_CONFIG_PATH="/opt/homebrew/opt/ffmpeg@7/lib/pkgconfig"
```

**Windows (winget):**
```powershell
winget install --id=Gyan.FFmpeg -e
# Or with Chocolatey:
# choco install ffmpeg
# Verify:
ffmpeg -version
```

If installing manually, download a build from https://www.gyan.dev/ffmpeg/builds/ and add its `bin\` directory to the `Path` environment variable.

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg libavdevice-dev libavfilter-dev libavformat-dev libavcodec-dev libswresample-dev libswscale-dev
```

### 2. Create Virtual Environment

```bash
cd agent
python -m venv venv

# Activate:
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVER_URL` | WebSocket signaling server URL | `ws://localhost:8000/ws/signaling` |
| `AGENT_ID` | Unique agent identifier | System hostname |
| `AGENT_TOKEN` | Authorization token (required) — must match an entry in the server's `AGENT_TOKENS` | None |

### Command-Line Arguments

| Argument | Short | Description | Default |
|----------|-------|-------------|---------|
| `--server` | `-s` | Server WebSocket URL | `ws://localhost:8000/ws/signaling` |
| `--agent-id` | `-i` | Agent identifier | System hostname |
| `--token` | `-t` | Authorization token (required) | None |
| `--monitor` | `-m` | Monitor number (1=primary) | `1` |
| `--fps` | `-f` | Target frames per second | `30` |
| `--scale` | | Resolution scale factor | `1.0` |

## Usage

### Basic Usage

**macOS / Linux:**
```bash
source venv/bin/activate
python main.py --server ws://server:8000/ws/signaling --token "$AGENT_TOKEN"
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
python main.py --server ws://server:8000/ws/signaling --token $env:AGENT_TOKEN
```

**Windows (cmd.exe):**
```cmd
venv\Scripts\activate.bat
python main.py --server ws://server:8000/ws/signaling --token %AGENT_TOKEN%
```

### Examples

**Custom agent ID**

```bash
python main.py -s ws://server:8000/ws/signaling -t "$AGENT_TOKEN" -i workstation-1
```

**Capture secondary monitor**

```bash
python main.py -s ws://server:8000/ws/signaling -t "$AGENT_TOKEN" --monitor 2
```

**Performance tuning (lower bandwidth)**

```bash
python main.py -s ws://server:8000/ws/signaling -t "$AGENT_TOKEN" --fps 15 --scale 0.75
```

**Production with SSL**

```bash
python main.py -s wss://remote.example.com/ws/signaling -t "$AGENT_TOKEN"
```

**Run via environment variables** (no CLI flags)

macOS / Linux:
```bash
export SERVER_URL=wss://remote.example.com/ws/signaling
export AGENT_TOKEN=auth_token_here
python main.py
```
Windows (PowerShell):
```powershell
$env:SERVER_URL  = "wss://remote.example.com/ws/signaling"
$env:AGENT_TOKEN = "auth_token_here"
python main.py
```

### List Available Monitors

```python
from screen_capture import ScreenCapture
ScreenCapture.list_monitors()
```

## How It Works

1. **Connect** - Agent connects to the signaling server via WebSocket
2. **Register** - Authenticates with password/token and registers its agent ID
3. **Wait** - Listens for WebRTC offers from browser clients
4. **Stream** - Creates peer connection, captures screen, streams via WebRTC
5. **Input** - Receives mouse/keyboard commands via WebRTC data channel
6. **Inject** - Injects input into the operating system via pynput

## Troubleshooting

### Connection Issues

- Verify the server URL is correct and server is running
- Check firewall allows WebSocket connections
- For `wss://`, ensure SSL certificates are valid

### Video Not Streaming

- Verify ffmpeg is installed: `ffmpeg -version`
- Check monitor index exists: use `list_monitors()` to see available monitors
- Try lower FPS/scale if bandwidth is limited

### Input Not Working

- **Linux**: May require adding user to `input` group
- **macOS**: Grant accessibility permissions in System Preferences
- **Windows**: Run as administrator if needed

### High CPU/Memory

- Lower FPS: `--fps 15`
- Reduce resolution: `--scale 0.5`
- Check for other screen recording software conflicts

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| aiortc | >=1.6.0 | WebRTC implementation |
| mss | >=9.0.0 | Fast screen capture |
| pynput | >=1.7.6 | Mouse/keyboard injection |
| websockets | >=12.0 | WebSocket client |
| av | >=11.0.0 | Video encoding (aiortc dep) |
| Pillow | >=10.0.0 | Image processing |
| numpy | >=1.24.0 | Array operations |

## License

See the main project repository for license information.

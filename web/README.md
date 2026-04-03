# Remote Control Web Client

A React-based browser client for remote desktop control. Connects to a signaling server and streams video from remote agents via WebRTC while capturing and transmitting mouse/keyboard input.

## Features

- Real-time video streaming via WebRTC peer-to-peer connection
- Low-latency mouse and keyboard input transmission
- Pointer Lock API for accurate relative mouse movement
- Fullscreen mode with F11 shortcut
- Live connection statistics (FPS, latency, bitrate, resolution)
- Quality indicator with visual feedback (excellent/good/fair/poor)
- Auto-reconnection on disconnect
- Password authentication
- Google OAuth support (optional)

## Prerequisites

- Node.js 18+ (latest LTS recommended)
- npm or yarn
- Running signaling server (see `server/` directory)

## Installation

### 1. Install Dependencies

```bash
cd web
npm install
```

### 2. Configure Environment (Optional)

Create a `.env` file for custom configuration:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/signaling
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

### 3. Development Server

```bash
npm run dev
```

Opens at `http://localhost:5173` with hot module replacement.

### 4. Production Build

```bash
npm run build
```

Output in `dist/` directory, ready for static hosting.

### 5. Preview Production Build

```bash
npm run preview
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Server REST API base URL | `http://localhost:8000` |
| `VITE_WS_URL` | WebSocket signaling server URL | `ws://localhost:8000/ws/signaling` |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID | None (Google login disabled) |

### Production Configuration

For production, update environment variables to use your server's domain:

```env
VITE_API_URL=https://your-server.com
VITE_WS_URL=wss://your-server.com/ws/signaling
```

## Usage

### Connecting to a Remote Agent

1. Open the web client in your browser
2. Login with password or Google account
3. Select an available agent from the dropdown
4. Click the "Connect" button
5. Wait for WebRTC connection to establish
6. Click the video area to start controlling

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Click video | Start mouse/keyboard capture |
| Escape | Release input capture |
| F11 | Toggle fullscreen mode |

### Status Indicators

- **Signaling**: WebSocket connection to signaling server
- **WebRTC**: Peer connection state to agent
- **Quality**: Connection quality based on metrics

### Quality Levels

| Level | Description |
|-------|-------------|
| Excellent | Score 80+, green indicator |
| Good | Score 60-79, yellow indicator |
| Fair | Score 40-59, orange indicator |
| Poor | Score below 40, red indicator |

## Docker

### Build Image

```bash
docker build -t remote-control-web .
```

### Build with Custom API URL

```bash
docker build \
  --build-arg VITE_API_URL=https://api.example.com \
  --build-arg VITE_WS_URL=wss://api.example.com/ws/signaling \
  -t remote-control-web .
```

### Run Container

```bash
docker run -p 80:80 remote-control-web
```

## Troubleshooting

### Video Not Showing

- Verify the agent is connected (check agent list)
- Click "Refresh" to reload available agents
- Check browser console for WebRTC errors
- Ensure agent has screen capture permissions

### Input Not Working

- Click the video area to activate pointer lock
- Check if browser is requesting pointer lock permission
- Verify data channel is open in browser DevTools
- Ensure agent has input injection permissions

### Connection Fails

- Verify server URL is correct
- Check browser console for WebSocket errors
- Ensure CORS is configured on server
- Try different browser to rule out extension conflicts

### Google Login Not Appearing

- Set `VITE_GOOGLE_CLIENT_ID` environment variable
- Rebuild the application after setting the variable
- Verify Google Cloud Console OAuth configuration

### High Latency

- Check network connection quality
- Try connecting from a different network
- Reduce agent capture resolution or FPS
- Check if TURN server is needed for NAT traversal

## Browser Support

| Browser | Version | Notes |
|---------|---------|-------|
| Chrome | 80+ | Full support |
| Firefox | 75+ | Full support |
| Edge | 80+ | Full support |
| Safari | 14+ | Limited WebRTC support, may need polyfills |

### Required Browser APIs

- WebRTC (RTCPeerConnection, RTCDataChannel)
- WebSocket
- Pointer Lock API
- Fullscreen API
- LocalStorage

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| react | ^19.0.0 | UI framework |
| react-dom | ^19.0.0 | DOM rendering |
| react-router-dom | ^7.0.0 | Client-side routing |
| @react-oauth/google | ^0.12.1 | Google Sign-In integration |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| vite | ^7.0.0 | Build tool and dev server |
| typescript | ^5.6.0 | Type checking |
| @vitejs/plugin-react | ^5.0.0 | React Fast Refresh |
| eslint | ^9.0.0 | Code linting |

## Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

## License

See the main project repository for license information.

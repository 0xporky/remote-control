# Web Client Development Guide

Technical reference for developing and debugging the Remote Control Web Client.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                               App.tsx                                        │
│                        (Routing + Google OAuth)                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                          Routes                                          ││
│  │  ┌─────────────────────┐    ┌───────────────────────────────────────┐  ││
│  │  │    /login           │    │            /desktop                    │  ││
│  │  │  ┌───────────────┐  │    │  ┌─────────────────────────────────┐  │  ││
│  │  │  │  LoginForm    │  │    │  │        DesktopView              │  │  ││
│  │  │  │ - Password    │  │    │  │  ┌─────────┬────────┬────────┐  │  │  ││
│  │  │  │ - Google OAuth│  │    │  │  │AgentSel.│Remote  │StatusBar│  │  │  ││
│  │  │  └───────────────┘  │    │  │  │         │Desktop │         │  │  │  ││
│  │  └─────────────────────┘    │  │  └─────────┴────────┴────────┘  │  │  ││
│  │                              │  └─────────────────────────────────┘  │  ││
│  │                              └───────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                │
         ▼                              ▼                ▼
┌─────────────────┐          ┌─────────────────┐  ┌─────────────────┐
│  services/      │          │    hooks/       │  │  Browser APIs   │
│  auth.ts        │◄─────────│  useSignaling   │  │  - WebRTC       │
│  signaling.ts   │          │  useWebRTC      │  │  - WebSocket    │
│  webrtc.ts      │          │  useInputCapture│  │  - Pointer Lock │
└─────────────────┘          │  useFullscreen  │  │  - Fullscreen   │
                              │  useConnStats   │  └─────────────────┘
                              └─────────────────┘
```

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 19.2.0 | UI framework |
| TypeScript | 5.9.3 | Type safety |
| Vite | 7.2.4 | Build tool with HMR |
| React Router DOM | 7.12.0 | Client-side routing |
| @react-oauth/google | 0.12.1 | Google Sign-In |

## File Descriptions

| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `main.tsx` | 10 | React entry point, renders App | - |
| `App.tsx` | 157 | Routing, Google OAuth provider | `App` |
| `types/index.ts` | 144 | TypeScript interfaces | All type definitions |
| `services/auth.ts` | 67 | JWT auth, token storage | `login`, `loginWithGoogle`, `getToken` |
| `services/signaling.ts` | 193 | WebSocket signaling client | `SignalingService` |
| `services/webrtc.ts` | 128 | RTCPeerConnection management | `WebRTCService` |
| `hooks/useSignaling.ts` | 89 | Signaling connection state | `useSignaling` |
| `hooks/useWebRTC.ts` | 177 | WebRTC lifecycle management | `useWebRTC` |
| `hooks/useInputCapture.ts` | 177 | Pointer Lock, input events | `useInputCapture` |
| `hooks/useConnectionStats.ts` | 185 | RTCStats collection | `useConnectionStats` |
| `hooks/useFullscreen.ts` | 70 | Fullscreen API wrapper | `useFullscreen` |
| `components/LoginForm.tsx` | 100 | Login UI | `LoginForm` |
| `components/RemoteDesktop.tsx` | 185 | Video display, input capture | `RemoteDesktop` |
| `components/StatusBar.tsx` | 119 | Metrics display | `StatusBar` |
| `components/AgentSelector.tsx` | 45 | Agent dropdown | `AgentSelector` |
| `styles/index.css` | 642 | All styling | - |

## Key Services

### SignalingService (services/signaling.ts)

WebSocket client for server communication.

```typescript
class SignalingService {
  constructor(url?: string)

  // Connection
  connect(): void
  disconnect(): void

  // Signaling
  authenticate(token: string): void
  requestAgentList(): void
  sendOffer(agentId: string, sdp: string): void
  sendIceCandidate(agentId: string, candidate: RTCIceCandidateInit): void

  // Callbacks
  onOpen(callback: () => void): void
  onClose(callback: () => void): void
  onError(callback: (error: Event) => void): void
  onAgentList(callback: (agents: string[]) => void): void
  onAnswer(callback: (agentId: string, sdp: string) => void): void
  onIceCandidate(callback: (agentId: string, candidate: RTCIceCandidateInit) => void): void
}
```

**Reconnection Behavior:**
- Automatic reconnect on disconnect
- Exponential backoff: `1000ms * 2^attempt`
- Maximum 5 reconnect attempts

### WebRTCService (services/webrtc.ts)

Manages RTCPeerConnection for video streaming.

```typescript
class WebRTCService {
  constructor(
    onTrack: (stream: MediaStream) => void,
    onIceCandidate: (candidate: RTCIceCandidate) => void,
    onConnectionStateChange: (state: RTCPeerConnectionState) => void
  )

  // Connection
  createOffer(): Promise<RTCSessionDescriptionInit>
  handleAnswer(sdp: string): Promise<void>
  addIceCandidate(candidate: RTCIceCandidateInit): Promise<void>
  close(): void

  // Input
  sendInput(event: InputEvent): void

  // State
  getConnectionState(): RTCPeerConnectionState
  isDataChannelOpen(): boolean
  getPeerConnection(): RTCPeerConnection | null
}
```

**STUN Servers:**
- `stun:stun.l.google.com:19302`
- `stun:stun1.l.google.com:19302`

**Data Channel:**
- Name: `"input"`
- Ordered: `true`

### Auth Service (services/auth.ts)

JWT token management.

```typescript
// Token storage (localStorage key: "remote_control_token")
function getToken(): string | null
function saveToken(token: string): void
function removeToken(): void
function isAuthenticated(): boolean

// Login methods
async function login(credentials: LoginCredentials): Promise<AuthResponse>
async function loginWithGoogle(credentials: GoogleLoginCredentials): Promise<AuthResponse>
```

## Custom Hooks

### useSignaling

```typescript
function useSignaling(): {
  isConnected: boolean;
  agents: string[];
  clientId: string | null;
  service: SignalingService | null;
  connect: () => void;
  disconnect: () => void;
  refreshAgents: () => void;
}
```

### useWebRTC

```typescript
function useWebRTC(
  signalingService: SignalingService | null,
  selectedAgent: string | null
): {
  stream: MediaStream | null;
  connectionState: RTCPeerConnectionState;
  isDataChannelOpen: boolean;
  peerConnection: RTCPeerConnection | null;
  reconnectAttempts: number;
  connect: () => Promise<void>;
  disconnect: () => void;
  sendInput: (event: InputEvent) => void;
}
```

### useInputCapture

```typescript
function useInputCapture(
  videoRef: RefObject<HTMLVideoElement>,
  onInput: (event: InputEvent) => void,
  enabled: boolean
): {
  isCapturing: boolean;
  requestCapture: () => void;
  releaseCapture: () => void;
}
```

### useConnectionStats

```typescript
interface ConnectionStats {
  fps: number;
  latency: number;        // ms
  jitter: number;         // ms
  packetLoss: number;     // percentage
  bitrate: number;        // kbps
  resolution: { width: number; height: number };
  quality: 'excellent' | 'good' | 'fair' | 'poor';
  qualityScore: number;   // 0-100
}

function useConnectionStats(
  peerConnection: RTCPeerConnection | null,
  pollingInterval?: number  // default: 1000ms
): ConnectionStats | null
```

**Quality Scoring:**
- Excellent: score >= 80
- Good: score >= 60
- Fair: score >= 40
- Poor: score < 40

### useFullscreen

```typescript
function useFullscreen(elementRef: RefObject<HTMLElement>): {
  isFullscreen: boolean;
  enterFullscreen: () => Promise<void>;
  exitFullscreen: () => Promise<void>;
  toggleFullscreen: () => Promise<void>;
}
```

## Data Flow

### Authentication Flow

```
User enters password
        │
        ▼
LoginForm.handleSubmit()
        │
        ▼
auth.login({ password })
        │
        ▼
POST /api/auth/login (URL-encoded)
        │
        ▼
{ access_token, token_type }
        │
        ▼
localStorage.setItem("remote_control_token", token)
        │
        ▼
navigate("/desktop")
```

### WebRTC Connection Flow

```
1. Signaling Connect
   useSignaling.connect() → WebSocket open
           │
           ▼
   SignalingService.authenticate(token)
           │
           ▼
   Server: { type: "authenticated", client_id }
           │
           ▼
   SignalingService.requestAgentList()
           │
           ▼
   Server: { type: "agent-list", agents: [...] }

2. WebRTC Offer
   useWebRTC.connect()
           │
           ▼
   WebRTCService.createOffer()
           │
           ▼
   new RTCPeerConnection() + addTransceiver("video", { direction: "recvonly" })
           │
           ▼
   createDataChannel("input", { ordered: true })
           │
           ▼
   pc.createOffer() → pc.setLocalDescription()
           │
           ▼
   SignalingService.sendOffer(agentId, sdp)

3. Answer & ICE
   Server: { type: "answer", agent_id, sdp }
           │
           ▼
   WebRTCService.handleAnswer(sdp)
           │
           ▼
   pc.setRemoteDescription(answer)
           │
           ▼
   ICE candidates exchanged bidirectionally
           │
           ▼
   connectionState → "connected"
           │
           ▼
   ontrack event → video stream received
```

### Input Event Flow

```
User mouse/keyboard action
        │
        ▼
useInputCapture event handler
        │
        ▼
createInputEvent() → { type, dx, dy, button, key, code }
        │
        ▼
onInput callback → useWebRTC.sendInput()
        │
        ▼
WebRTCService.sendInput()
        │
        ▼
dataChannel.send(JSON.stringify(event))
        │
        ▼
Agent receives via data channel
```

## WebSocket Protocol

### Message Types

| Type | Direction | Fields | Purpose |
|------|-----------|--------|---------|
| `authenticate` | Client→Server | `token` | Send JWT for auth |
| `authenticated` | Server→Client | `client_id` | Confirm auth success |
| `error` | Server→Client | `message` | Error notification |
| `list-agents` | Client→Server | - | Request agent list |
| `agent-list` | Server→Client | `agents[]` | Available agents |
| `offer` | Client→Server→Agent | `target`, `sdp` | SDP offer |
| `answer` | Agent→Server→Client | `target`, `sdp` | SDP answer |
| `ice-candidate` | Bidirectional | `target`, `candidate` | ICE candidate |

### Example Messages

```typescript
// Authenticate
{ "type": "authenticate", "token": "eyJhbGci..." }

// Request agents
{ "type": "list-agents" }

// Send offer
{ "type": "offer", "target": "agent-hostname", "sdp": "v=0\r\n..." }

// Receive answer
{ "type": "answer", "agent_id": "agent-hostname", "sdp": "v=0\r\n..." }

// ICE candidate
{ "type": "ice-candidate", "target": "agent-hostname", "candidate": {...} }
```

## Input Event Format

### Mouse Events

```typescript
// Relative movement (Pointer Lock)
{ type: "mousemove", dx: number, dy: number }

// Button press/release (0=left, 1=middle, 2=right)
{ type: "mousedown" | "mouseup", button: 0 | 1 | 2 }

// Scroll wheel
{ type: "wheel", deltaX: number, deltaY: number }
```

### Keyboard Events

```typescript
{ type: "keydown" | "keyup", key: string, code: string }

// Examples:
{ type: "keydown", key: "a", code: "KeyA" }
{ type: "keydown", key: "Enter", code: "Enter" }
{ type: "keydown", key: "Shift", code: "ShiftLeft" }
```

## Type Definitions

### Core Types (types/index.ts)

```typescript
// Auth
interface LoginCredentials { password: string }
interface GoogleLoginCredentials { credential: string }
interface AuthResponse { access_token: string; token_type: string }
interface Agent { id: string; name?: string; connected_at?: string }

// Connection states
type ConnectionState = 'new' | 'connecting' | 'connected' | 'disconnected' | 'failed' | 'closed'

// Input events
type InputEvent = MouseMoveEvent | MouseButtonEvent | WheelEvent | KeyEvent

interface MouseMoveEvent { type: 'mousemove'; dx: number; dy: number }
interface MouseButtonEvent { type: 'mousedown' | 'mouseup'; button: number }
interface WheelEvent { type: 'wheel'; deltaX: number; deltaY: number }
interface KeyEvent { type: 'keydown' | 'keyup'; key: string; code: string }

// Signaling messages
type SignalingMessage =
  | AuthenticateMessage | AuthenticatedMessage | ErrorMessage
  | AgentListMessage | OfferMessage | AnswerMessage | IceCandidateMessage
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.2.0 | UI framework |
| react-dom | 19.2.0 | DOM rendering |
| react-router-dom | 7.12.0 | Client-side routing |
| @react-oauth/google | 0.12.1 | Google Sign-In SDK |
| vite | 7.2.4 | Build tool |
| typescript | 5.9.3 | Type checking |
| @vitejs/plugin-react | 5.1.1 | React Fast Refresh |
| eslint | 9.39.1 | Code linting |
| @typescript-eslint/* | 8.46.4 | TypeScript ESLint |

## Debugging

### Browser DevTools

**Network Tab:**
- Filter by `WS` to see WebSocket frames
- Check request/response headers
- Monitor message timing

**Console:**
- Connection state changes logged
- Error messages from services
- Input event debugging

**Application Tab:**
- LocalStorage: `remote_control_token`
- Check token presence and validity

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No video | Agent not connected | Refresh agent list, verify agent running |
| No video | WebRTC state stuck | Check ICE candidates, try TURN server |
| No input | Pointer lock not active | Click video element to capture |
| No input | Data channel closed | Check connectionState, reconnect |
| Reconnect loop | Invalid credentials | Check token, re-authenticate |
| Google button missing | No client ID | Set VITE_GOOGLE_CLIENT_ID |

### Testing Components

**Test authentication:**
```javascript
// In browser console
localStorage.getItem("remote_control_token")
// Should return JWT string after login
```

**Test signaling:**
```javascript
// In Network tab, filter by WS
// Look for messages: authenticate → authenticated → list-agents → agent-list
```

**Test WebRTC stats:**
```javascript
// If pc is the RTCPeerConnection
const stats = await pc.getStats();
stats.forEach(report => {
  if (report.type === 'inbound-rtp' && report.kind === 'video') {
    console.log('FPS:', report.framesPerSecond);
    console.log('Frames received:', report.framesReceived);
  }
});
```

## CSS Architecture

### Design System

```css
/* Color palette */
--color-primary: #1a1a2e;      /* Dark background */
--color-secondary: #16213e;    /* Slightly lighter */
--color-accent: #e94560;       /* Red accent */
--color-success: #4ade80;      /* Green */
--color-warning: #fbbf24;      /* Yellow */
--color-error: #f87171;        /* Red */

/* Quality indicators */
--quality-excellent: #22c55e;  /* Green */
--quality-good: #eab308;       /* Yellow */
--quality-fair: #f97316;       /* Orange */
--quality-poor: #ef4444;       /* Red */
```

### Component Styling

- Login form: Centered card with dark theme
- Status bar: Fixed top bar with connection indicators
- Agent selector: Styled dropdown with refresh button
- Remote desktop: Full-height video container with overlays
- Quality bars: Animated visual indicators

### Responsive Design

- Mobile breakpoint: 768px
- Flexible layouts using flexbox
- Touch-friendly controls for mobile

## Configuration Reference

### Vite Config (vite.config.ts)

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
```

### TypeScript Config (tsconfig.app.json)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true
  }
}
```

### Environment Variables

| Variable | Used In | Purpose |
|----------|---------|---------|
| `VITE_API_URL` | `services/auth.ts` | REST API base URL |
| `VITE_WS_URL` | `services/signaling.ts` | WebSocket URL |
| `VITE_GOOGLE_CLIENT_ID` | `App.tsx` | Google OAuth client ID |

## Extending the Client

### Adding New Input Types

1. Define event type in `types/index.ts`:
```typescript
interface TouchEvent {
  type: 'touch';
  touches: Array<{ x: number; y: number }>;
}
```

2. Add handler in `useInputCapture.ts`:
```typescript
const handleTouch = (e: TouchEvent) => {
  const touches = Array.from(e.touches).map(t => ({
    x: t.clientX, y: t.clientY
  }));
  onInput({ type: 'touch', touches });
};
```

3. Register event listener for `touchstart`, `touchmove`, `touchend`.

### Adding Connection Quality Metrics

Extend `useConnectionStats.ts`:
```typescript
// Add new metric
interface ConnectionStats {
  // existing...
  networkType?: string;  // e.g., "4g", "wifi"
}

// Collect from RTCStatsReport
stats.forEach(report => {
  if (report.type === 'candidate-pair' && report.state === 'succeeded') {
    // Extract network info
  }
});
```

### Custom Theming

Override CSS variables in `styles/index.css`:
```css
:root {
  --color-primary: #your-color;
  --color-accent: #your-accent;
}
```

// Authentication types
export interface LoginCredentials {
  password: string;
}

export interface GoogleLoginCredentials {
  credential: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
}

// Agent types
export interface Agent {
  id: string;
  name?: string;
  connected_at?: string;
}

// Signaling message types
export type SignalingMessageType =
  | 'authenticate'
  | 'authenticated'
  | 'error'
  | 'agent-list'
  | 'connect'
  | 'offer'
  | 'answer'
  | 'ice-candidate'
  | 'disconnected';

export interface SignalingMessage {
  type: SignalingMessageType;
  [key: string]: unknown;
}

export interface AuthenticateMessage extends SignalingMessage {
  type: 'authenticate';
  token: string;
}

export interface AuthenticatedMessage extends SignalingMessage {
  type: 'authenticated';
  client_id: string;
}

export interface ErrorMessage extends SignalingMessage {
  type: 'error';
  message: string;
}

export interface AgentListMessage extends SignalingMessage {
  type: 'agent-list';
  agents: string[];
}

export interface ConnectMessage extends SignalingMessage {
  type: 'connect';
  target: string;
}

export interface OfferMessage extends SignalingMessage {
  type: 'offer';
  sdp: string;
  target: string;
}

export interface AnswerMessage extends SignalingMessage {
  type: 'answer';
  sdp: string;
  from: string;
}

export interface IceCandidateMessage extends SignalingMessage {
  type: 'ice-candidate';
  candidate: RTCIceCandidateInit;
  target?: string;
  from?: string;
}

// WebRTC types
export type ConnectionState =
  | 'new'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'failed'
  | 'closed';

export interface WebRTCState {
  connectionState: ConnectionState;
  iceConnectionState: RTCIceConnectionState;
  stream: MediaStream | null;
}

// Input event types (for Step 8)
export type InputEventType =
  | 'mousemove'
  | 'mousedown'
  | 'mouseup'
  | 'wheel'
  | 'keydown'
  | 'keyup';

export interface BaseInputEvent {
  type: InputEventType;
}

export interface MouseMoveEvent extends BaseInputEvent {
  type: 'mousemove';
  dx: number;
  dy: number;
}

export interface MouseButtonEvent extends BaseInputEvent {
  type: 'mousedown' | 'mouseup';
  button: number;
}

export interface WheelEvent extends BaseInputEvent {
  type: 'wheel';
  deltaX: number;
  deltaY: number;
}

export interface KeyEvent extends BaseInputEvent {
  type: 'keydown' | 'keyup';
  key: string;
  code: string;
}

export type InputEvent =
  | MouseMoveEvent
  | MouseButtonEvent
  | WheelEvent
  | KeyEvent;

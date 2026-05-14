import { getToken } from './auth';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const STUN_FALLBACK: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

interface TurnResponse {
  iceServers: RTCIceServer[];
}

export async function fetchIceServers(): Promise<RTCIceServer[]> {
  const token = getToken();
  if (!token) {
    return STUN_FALLBACK;
  }

  try {
    const response = await fetch(`${API_BASE}/api/turn-credentials`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      console.warn('TURN creds fetch failed:', response.status);
      return STUN_FALLBACK;
    }
    const data: TurnResponse = await response.json();
    return [...STUN_FALLBACK, ...data.iceServers];
  } catch (err) {
    console.warn('TURN creds fetch error, falling back to STUN-only:', err);
    return STUN_FALLBACK;
  }
}

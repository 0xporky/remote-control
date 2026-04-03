import { useState, useCallback, useRef, useEffect } from 'react';
import { WebRTCService } from '../services/webrtc';
import { SignalingService } from '../services/signaling';
import type { ConnectionState, InputEvent } from '../types';

interface UseWebRTCOptions {
  autoReconnect?: boolean;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

interface UseWebRTCResult {
  stream: MediaStream | null;
  connectionState: ConnectionState;
  isDataChannelOpen: boolean;
  peerConnection: RTCPeerConnection | null;
  reconnectAttempts: number;
  connect: (agentId: string) => Promise<void>;
  disconnect: () => void;
  sendInput: (event: InputEvent) => void;
}

const DEFAULT_OPTIONS: UseWebRTCOptions = {
  autoReconnect: true,
  reconnectDelay: 2000,
  maxReconnectAttempts: 5,
};

export function useWebRTC(
  signaling: SignalingService | null,
  options: UseWebRTCOptions = {}
): UseWebRTCResult {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('new');
  const [isDataChannelOpen, setIsDataChannelOpen] = useState(false);
  const [peerConnection, setPeerConnection] = useState<RTCPeerConnection | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const serviceRef = useRef<WebRTCService | null>(null);
  const targetAgentRef = useRef<string | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalDisconnectRef = useRef(false);

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const connect = useCallback(async (agentId: string) => {
    if (!signaling?.isConnected) {
      console.error('Signaling not connected');
      return;
    }

    // Clear any pending reconnect
    clearReconnectTimeout();
    intentionalDisconnectRef.current = false;

    // Clean up existing connection
    serviceRef.current?.close();

    const webrtc = new WebRTCService();
    serviceRef.current = webrtc;
    targetAgentRef.current = agentId;
    setPeerConnection(webrtc.peerConnection);

    webrtc.onTrack((mediaStream) => {
      setStream(mediaStream);
    });

    webrtc.onConnectionState((state) => {
      setConnectionState(state);

      // Handle auto-reconnect on connection failure
      if (
        opts.autoReconnect &&
        !intentionalDisconnectRef.current &&
        (state === 'failed' || state === 'disconnected')
      ) {
        const attempts = reconnectAttempts + 1;
        setReconnectAttempts(attempts);

        if (attempts <= (opts.maxReconnectAttempts || 5)) {
          console.log(`Connection ${state}, attempting reconnect (${attempts}/${opts.maxReconnectAttempts})`);

          reconnectTimeoutRef.current = setTimeout(() => {
            if (targetAgentRef.current && signaling?.isConnected) {
              connect(targetAgentRef.current);
            }
          }, opts.reconnectDelay);
        } else {
          console.log('Max reconnect attempts reached');
        }
      }

      // Reset reconnect attempts on successful connection
      if (state === 'connected') {
        setReconnectAttempts(0);
      }
    });

    webrtc.onIceCandidate((candidate) => {
      signaling.sendIceCandidate(agentId, candidate.toJSON());
    });

    webrtc.onDataChannelOpen(() => {
      setIsDataChannelOpen(true);
    });

    webrtc.onDataChannelClose(() => {
      setIsDataChannelOpen(false);
    });

    // Set up signaling handlers for this connection
    signaling.onAnswer((fromAgent, sdp) => {
      if (fromAgent === agentId) {
        webrtc.handleAnswer(sdp);
      }
    });

    signaling.onIceCandidate((fromAgent, candidate) => {
      if (fromAgent === agentId) {
        webrtc.addIceCandidate(candidate);
      }
    });

    // Create and send offer
    try {
      setConnectionState('connecting');
      const offer = await webrtc.createOffer();
      signaling.sendOffer(agentId, offer.sdp!);
    } catch (err) {
      console.error('Failed to create offer:', err);
      setConnectionState('failed');
    }
  }, [signaling, opts.autoReconnect, opts.reconnectDelay, opts.maxReconnectAttempts, reconnectAttempts, clearReconnectTimeout]);

  const disconnect = useCallback(() => {
    intentionalDisconnectRef.current = true;
    clearReconnectTimeout();
    serviceRef.current?.close();
    serviceRef.current = null;
    targetAgentRef.current = null;
    setPeerConnection(null);
    setStream(null);
    setConnectionState('closed');
    setIsDataChannelOpen(false);
    setReconnectAttempts(0);
  }, [clearReconnectTimeout]);

  const sendInput = useCallback((event: InputEvent) => {
    serviceRef.current?.sendInput(event);
  }, []);

  useEffect(() => {
    return () => {
      clearReconnectTimeout();
      serviceRef.current?.close();
    };
  }, [clearReconnectTimeout]);

  return {
    stream,
    connectionState,
    isDataChannelOpen,
    peerConnection,
    reconnectAttempts,
    connect,
    disconnect,
    sendInput,
  };
}

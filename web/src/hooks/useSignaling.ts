import { useState, useEffect, useCallback, useRef } from 'react';
import { SignalingService } from '../services/signaling';
import { getToken } from '../services/auth';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/signaling';

interface UseSignalingResult {
  isConnected: boolean;
  agents: string[];
  clientId: string | null;
  service: SignalingService | null;
  connect: () => void;
  disconnect: () => void;
  refreshAgents: () => void;
}

export function useSignaling(): UseSignalingResult {
  const [isConnected, setIsConnected] = useState(false);
  const [agents, setAgents] = useState<string[]>([]);
  const [clientId, setClientId] = useState<string | null>(null);
  const serviceRef = useRef<SignalingService | null>(null);

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) {
      console.error('No token available');
      return;
    }

    if (serviceRef.current?.isConnected) {
      return;
    }

    const service = new SignalingService(WS_URL, token);

    service.onOpen(() => {
      setIsConnected(true);
      // Request agent list after connection
      setTimeout(() => service.requestAgentList(), 100);
    });

    service.onClose(() => {
      setIsConnected(false);
      setClientId(null);
    });

    service.onAgentList((agentList) => {
      setAgents(agentList);
    });

    service.onMessage((message) => {
      if (message.type === 'authenticated') {
        setClientId((message as unknown as { client_id: string }).client_id);
      }
    });

    serviceRef.current = service;
    service.connect();
  }, []);

  const disconnect = useCallback(() => {
    serviceRef.current?.disconnect();
    serviceRef.current = null;
    setIsConnected(false);
    setAgents([]);
    setClientId(null);
  }, []);

  const refreshAgents = useCallback(() => {
    serviceRef.current?.requestAgentList();
  }, []);

  useEffect(() => {
    return () => {
      serviceRef.current?.disconnect();
    };
  }, []);

  return {
    isConnected,
    agents,
    clientId,
    service: serviceRef.current,
    connect,
    disconnect,
    refreshAgents,
  };
}

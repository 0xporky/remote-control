import type {
  SignalingMessage,
  AnswerMessage,
  IceCandidateMessage,
  AgentListMessage,
} from '../types';

type MessageHandler = (message: SignalingMessage) => void;

export class SignalingService {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string;
  private clientId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  private onOpenCallback: (() => void) | null = null;
  private onCloseCallback: (() => void) | null = null;
  private onErrorCallback: ((error: Event) => void) | null = null;
  private onAgentListCallback: ((agents: string[]) => void) | null = null;
  private onAnswerCallback: ((agentId: string, sdp: string) => void) | null = null;
  private onIceCandidateCallback: ((agentId: string, candidate: RTCIceCandidateInit) => void) | null = null;
  private messageHandlers: MessageHandler[] = [];

  constructor(url: string, token: string) {
    this.url = url;
    this.token = token;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.authenticate();
      this.onOpenCallback?.();
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.onCloseCallback?.();
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.onErrorCallback?.(error);
    };

    this.ws.onmessage = (event) => {
      try {
        const message: SignalingMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (err) {
        console.error('Failed to parse message:', err);
      }
    };
  }

  private authenticate(): void {
    this.send({
      type: 'authenticate',
      token: this.token,
    });
  }

  private handleMessage(message: SignalingMessage): void {
    console.log('Received message:', message.type);

    switch (message.type) {
      case 'authenticated':
        this.clientId = (message as unknown as { client_id: string }).client_id;
        console.log('Authenticated as:', this.clientId);
        break;

      case 'error':
        console.error('Server error:', (message as unknown as { message: string }).message);
        break;

      case 'agent-list':
        const agentList = message as AgentListMessage;
        this.onAgentListCallback?.(agentList.agents);
        break;

      case 'answer':
        const answer = message as AnswerMessage;
        this.onAnswerCallback?.(answer.from, answer.sdp);
        break;

      case 'ice-candidate':
        const iceMsg = message as IceCandidateMessage;
        if (iceMsg.from && iceMsg.candidate) {
          this.onIceCandidateCallback?.(iceMsg.from, iceMsg.candidate);
        }
        break;
    }

    this.messageHandlers.forEach((handler) => handler(message));
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  private send(message: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }

  sendOffer(agentId: string, sdp: string): void {
    this.send({
      type: 'offer',
      target: agentId,
      sdp,
    });
  }

  sendIceCandidate(agentId: string, candidate: RTCIceCandidateInit): void {
    this.send({
      type: 'ice-candidate',
      target: agentId,
      candidate,
    });
  }

  requestAgentList(): void {
    this.send({ type: 'list-agents' });
  }

  onOpen(callback: () => void): void {
    this.onOpenCallback = callback;
  }

  onClose(callback: () => void): void {
    this.onCloseCallback = callback;
  }

  onError(callback: (error: Event) => void): void {
    this.onErrorCallback = callback;
  }

  onAgentList(callback: (agents: string[]) => void): void {
    this.onAgentListCallback = callback;
  }

  onAnswer(callback: (agentId: string, sdp: string) => void): void {
    this.onAnswerCallback = callback;
  }

  onIceCandidate(callback: (agentId: string, candidate: RTCIceCandidateInit) => void): void {
    this.onIceCandidateCallback = callback;
  }

  onMessage(handler: MessageHandler): void {
    this.messageHandlers.push(handler);
  }

  disconnect(): void {
    this.maxReconnectAttempts = 0; // Prevent reconnection
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get id(): string | null {
    return this.clientId;
  }
}

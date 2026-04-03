import type { ConnectionState, InputEvent } from '../types';

const ICE_SERVERS: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

export class WebRTCService {
  private pc: RTCPeerConnection;
  private dataChannel: RTCDataChannel | null = null;

  private onTrackCallback: ((stream: MediaStream) => void) | null = null;
  private onConnectionStateCallback: ((state: ConnectionState) => void) | null = null;
  private onIceCandidateCallback: ((candidate: RTCIceCandidate) => void) | null = null;
  private onDataChannelOpenCallback: (() => void) | null = null;
  private onDataChannelCloseCallback: (() => void) | null = null;

  constructor() {
    this.pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
    this.setupPeerConnection();
  }

  private setupPeerConnection(): void {
    this.pc.ontrack = (event) => {
      console.log('Track received:', event.track.kind);
      if (event.streams[0]) {
        this.onTrackCallback?.(event.streams[0]);
      }
    };

    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.onIceCandidateCallback?.(event.candidate);
      }
    };

    this.pc.onconnectionstatechange = () => {
      console.log('Connection state:', this.pc.connectionState);
      this.onConnectionStateCallback?.(this.pc.connectionState as ConnectionState);
    };

    this.pc.oniceconnectionstatechange = () => {
      console.log('ICE connection state:', this.pc.iceConnectionState);
    };
  }

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    // Add transceivers for receiving video and creating data channel
    this.pc.addTransceiver('video', { direction: 'recvonly' });

    // Create data channel for input
    this.dataChannel = this.pc.createDataChannel('input', {
      ordered: true,
    });

    this.dataChannel.onopen = () => {
      console.log('Data channel opened');
      this.onDataChannelOpenCallback?.();
    };

    this.dataChannel.onclose = () => {
      console.log('Data channel closed');
      this.onDataChannelCloseCallback?.();
    };

    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    return offer;
  }

  async handleAnswer(sdp: string): Promise<void> {
    const answer = new RTCSessionDescription({ type: 'answer', sdp });
    await this.pc.setRemoteDescription(answer);
  }

  async addIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    try {
      await this.pc.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (err) {
      console.error('Error adding ICE candidate:', err);
    }
  }

  sendInput(event: InputEvent): void {
    if (this.dataChannel?.readyState === 'open') {
      this.dataChannel.send(JSON.stringify(event));
    }
  }

  onTrack(callback: (stream: MediaStream) => void): void {
    this.onTrackCallback = callback;
  }

  onConnectionState(callback: (state: ConnectionState) => void): void {
    this.onConnectionStateCallback = callback;
  }

  onIceCandidate(callback: (candidate: RTCIceCandidate) => void): void {
    this.onIceCandidateCallback = callback;
  }

  onDataChannelOpen(callback: () => void): void {
    this.onDataChannelOpenCallback = callback;
  }

  onDataChannelClose(callback: () => void): void {
    this.onDataChannelCloseCallback = callback;
  }

  close(): void {
    this.dataChannel?.close();
    this.pc.close();
  }

  get connectionState(): ConnectionState {
    return this.pc.connectionState as ConnectionState;
  }

  get isDataChannelOpen(): boolean {
    return this.dataChannel?.readyState === 'open';
  }

  get peerConnection(): RTCPeerConnection {
    return this.pc;
  }
}

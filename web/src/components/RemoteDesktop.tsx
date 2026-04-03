import { useRef, useEffect, useCallback } from 'react';
import { useInputCapture } from '../hooks/useInputCapture';
import { useFullscreen } from '../hooks/useFullscreen';
import type { ConnectionState, InputEvent } from '../types';

interface RemoteDesktopProps {
  stream: MediaStream | null;
  connectionState: ConnectionState;
  onConnect: () => void;
  onDisconnect: () => void;
  isConnected: boolean;
  isDataChannelOpen: boolean;
  onInput: (event: InputEvent) => void;
  reconnectAttempts?: number;
}

export function RemoteDesktop({
  stream,
  connectionState,
  onConnect,
  onDisconnect,
  isConnected,
  isDataChannelOpen,
  onInput,
  reconnectAttempts = 0,
}: RemoteDesktopProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const canCapture = connectionState === 'connected' && !!stream && isDataChannelOpen;

  const { isCapturing, requestCapture, releaseCapture } = useInputCapture({
    videoRef,
    onInput,
    enabled: canCapture,
  });

  const { isFullscreen, toggleFullscreen } = useFullscreen(containerRef);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  // Release capture when disconnecting
  useEffect(() => {
    if (connectionState !== 'connected') {
      releaseCapture();
    }
  }, [connectionState, releaseCapture]);

  // Handle keyboard shortcut for fullscreen (F11)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F11' && canCapture) {
        e.preventDefault();
        toggleFullscreen();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [canCapture, toggleFullscreen]);

  const handleVideoClick = useCallback(() => {
    if (canCapture && !isCapturing) {
      requestCapture();
    }
  }, [canCapture, isCapturing, requestCapture]);

  const getStatusText = () => {
    switch (connectionState) {
      case 'new':
        return 'Not connected';
      case 'connecting':
        return 'Connecting...';
      case 'connected':
        return 'Connected';
      case 'disconnected':
        return reconnectAttempts > 0 ? `Reconnecting (${reconnectAttempts})...` : 'Disconnected';
      case 'failed':
        return reconnectAttempts > 0 ? `Reconnecting (${reconnectAttempts})...` : 'Connection failed';
      case 'closed':
        return 'Connection closed';
      default:
        return connectionState;
    }
  };

  const showOverlay = connectionState !== 'connected' || !stream;
  const showCapturePrompt = canCapture && !isCapturing;
  const isReconnecting = reconnectAttempts > 0 && (connectionState === 'disconnected' || connectionState === 'failed');

  return (
    <div ref={containerRef} className={`remote-desktop ${isFullscreen ? 'fullscreen' : ''}`}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className={`remote-video ${canCapture ? 'capturable' : ''}`}
        onClick={handleVideoClick}
      />

      {showOverlay && (
        <div className="remote-overlay">
          <div className="overlay-content">
            <p className="status-text">{getStatusText()}</p>

            {(connectionState === 'new' || connectionState === 'closed') && (
              <button
                onClick={onConnect}
                disabled={!isConnected}
                className="connect-button"
              >
                {isConnected ? 'Connect' : 'Waiting for signaling...'}
              </button>
            )}

            {connectionState === 'failed' && !isReconnecting && (
              <button
                onClick={onConnect}
                disabled={!isConnected}
                className="connect-button"
              >
                Retry
              </button>
            )}

            {(connectionState === 'connecting' || isReconnecting) && (
              <div className="connecting-spinner" />
            )}

            {connectionState === 'connected' && !stream && (
              <p className="waiting-text">Waiting for video stream...</p>
            )}
          </div>
        </div>
      )}

      {showCapturePrompt && (
        <div className="capture-prompt" onClick={handleVideoClick}>
          <span>Click to control</span>
          <span className="capture-hint">Press ESC to release | F11 for fullscreen</span>
        </div>
      )}

      {isCapturing && (
        <div className="capturing-indicator">
          <span className="capturing-dot" />
          <span>Controlling</span>
        </div>
      )}

      {connectionState === 'connected' && (
        <div className="desktop-controls">
          <button
            onClick={toggleFullscreen}
            className="control-button fullscreen-button"
            title={isFullscreen ? 'Exit Fullscreen (F11)' : 'Fullscreen (F11)'}
          >
            {isFullscreen ? (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
              </svg>
            )}
          </button>
          <button
            onClick={onDisconnect}
            className="control-button disconnect-button"
            title="Disconnect"
          >
            Disconnect
          </button>
        </div>
      )}
    </div>
  );
}

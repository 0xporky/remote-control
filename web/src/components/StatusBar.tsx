import type { ConnectionState } from '../types';
import type { ConnectionStats } from '../hooks/useConnectionStats';

interface StatusBarProps {
  signalingConnected: boolean;
  webrtcState: ConnectionState;
  clientId: string | null;
  stats: ConnectionStats | null;
  onLogout: () => void;
}

export function StatusBar({
  signalingConnected,
  webrtcState,
  clientId,
  stats,
  onLogout,
}: StatusBarProps) {
  const getWebRTCStatusClass = () => {
    switch (webrtcState) {
      case 'connected':
        return 'status-connected';
      case 'connecting':
        return 'status-connecting';
      case 'failed':
        return 'status-error';
      default:
        return 'status-disconnected';
    }
  };

  const getQualityClass = () => {
    if (!stats) return '';
    switch (stats.qualityLabel) {
      case 'excellent':
        return 'quality-excellent';
      case 'good':
        return 'quality-good';
      case 'fair':
        return 'quality-fair';
      case 'poor':
        return 'quality-poor';
      default:
        return '';
    }
  };

  const formatBitrate = (kbps: number) => {
    if (kbps >= 1000) {
      return `${(kbps / 1000).toFixed(1)} Mbps`;
    }
    return `${kbps} kbps`;
  };

  return (
    <div className="status-bar">
      <div className="status-left">
        <span className="status-item">
          <span
            className={`status-indicator ${signalingConnected ? 'status-connected' : 'status-disconnected'}`}
          />
          Signaling: {signalingConnected ? 'Connected' : 'Disconnected'}
        </span>

        <span className="status-item">
          <span className={`status-indicator ${getWebRTCStatusClass()}`} />
          WebRTC: {webrtcState}
        </span>

        {clientId && (
          <span className="status-item client-id">
            ID: {clientId.substring(0, 8)}...
          </span>
        )}
      </div>

      <div className="status-center">
        {stats && webrtcState === 'connected' && (
          <>
            <span className={`status-item quality-indicator ${getQualityClass()}`}>
              <span className="quality-bars">
                <span className={`quality-bar ${stats.quality >= 25 ? 'active' : ''}`} />
                <span className={`quality-bar ${stats.quality >= 50 ? 'active' : ''}`} />
                <span className={`quality-bar ${stats.quality >= 75 ? 'active' : ''}`} />
                <span className={`quality-bar ${stats.quality >= 90 ? 'active' : ''}`} />
              </span>
              {stats.qualityLabel}
            </span>

            <span className="status-item stats-item">
              {stats.fps > 0 && <span>{stats.fps} FPS</span>}
            </span>

            <span className="status-item stats-item">
              {stats.latency > 0 && <span>{stats.latency} ms</span>}
            </span>

            <span className="status-item stats-item">
              {stats.bitrate > 0 && <span>{formatBitrate(stats.bitrate)}</span>}
            </span>

            {stats.width > 0 && stats.height > 0 && (
              <span className="status-item stats-item resolution">
                {stats.width}x{stats.height}
              </span>
            )}
          </>
        )}
      </div>

      <div className="status-right">
        <button onClick={onLogout} className="logout-button">
          Logout
        </button>
      </div>
    </div>
  );
}

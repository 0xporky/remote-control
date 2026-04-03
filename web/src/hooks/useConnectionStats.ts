import { useState, useEffect, useCallback, useRef } from 'react';

export interface ConnectionStats {
  // Video stats
  fps: number;
  width: number;
  height: number;
  framesReceived: number;
  framesDropped: number;

  // Network stats
  latency: number; // RTT in ms
  jitter: number;
  packetsLost: number;
  packetsReceived: number;
  bytesReceived: number;
  bitrate: number; // kbps

  // Quality indicator (0-100)
  quality: number;
  qualityLabel: 'excellent' | 'good' | 'fair' | 'poor';
}

const DEFAULT_STATS: ConnectionStats = {
  fps: 0,
  width: 0,
  height: 0,
  framesReceived: 0,
  framesDropped: 0,
  latency: 0,
  jitter: 0,
  packetsLost: 0,
  packetsReceived: 0,
  bytesReceived: 0,
  bitrate: 0,
  quality: 0,
  qualityLabel: 'poor',
};

function calculateQuality(stats: Partial<ConnectionStats>): { quality: number; qualityLabel: ConnectionStats['qualityLabel'] } {
  let score = 100;

  // Penalize for high latency (>100ms starts reducing score)
  if (stats.latency && stats.latency > 50) {
    score -= Math.min(40, (stats.latency - 50) / 5);
  }

  // Penalize for packet loss
  if (stats.packetsReceived && stats.packetsLost) {
    const lossRate = stats.packetsLost / (stats.packetsReceived + stats.packetsLost);
    score -= Math.min(30, lossRate * 100);
  }

  // Penalize for high jitter (>30ms starts reducing score)
  if (stats.jitter && stats.jitter > 30) {
    score -= Math.min(15, (stats.jitter - 30) / 2);
  }

  // Penalize for dropped frames
  if (stats.framesReceived && stats.framesDropped) {
    const dropRate = stats.framesDropped / (stats.framesReceived + stats.framesDropped);
    score -= Math.min(15, dropRate * 100);
  }

  score = Math.max(0, Math.round(score));

  let qualityLabel: ConnectionStats['qualityLabel'];
  if (score >= 80) qualityLabel = 'excellent';
  else if (score >= 60) qualityLabel = 'good';
  else if (score >= 40) qualityLabel = 'fair';
  else qualityLabel = 'poor';

  return { quality: score, qualityLabel };
}

export function useConnectionStats(
  peerConnection: RTCPeerConnection | null,
  enabled: boolean = true,
  intervalMs: number = 1000
): ConnectionStats {
  const [stats, setStats] = useState<ConnectionStats>(DEFAULT_STATS);
  const prevStatsRef = useRef<{
    timestamp: number;
    bytesReceived: number;
    framesReceived: number;
  } | null>(null);

  const collectStats = useCallback(async () => {
    if (!peerConnection || peerConnection.connectionState !== 'connected') {
      return;
    }

    try {
      const report = await peerConnection.getStats();
      const newStats: Partial<ConnectionStats> = {};

      report.forEach((stat) => {
        // Inbound RTP (video)
        if (stat.type === 'inbound-rtp' && stat.kind === 'video') {
          newStats.framesReceived = stat.framesReceived || 0;
          newStats.framesDropped = stat.framesDropped || 0;
          newStats.bytesReceived = stat.bytesReceived || 0;
          newStats.packetsReceived = stat.packetsReceived || 0;
          newStats.packetsLost = stat.packetsLost || 0;
          newStats.jitter = (stat.jitter || 0) * 1000; // Convert to ms

          // Calculate FPS and bitrate from delta
          if (prevStatsRef.current && newStats.framesReceived !== undefined && newStats.bytesReceived !== undefined) {
            const timeDelta = (Date.now() - prevStatsRef.current.timestamp) / 1000;
            if (timeDelta > 0) {
              const framesDelta = newStats.framesReceived - prevStatsRef.current.framesReceived;
              newStats.fps = Math.round(framesDelta / timeDelta);

              const bytesDelta = newStats.bytesReceived - prevStatsRef.current.bytesReceived;
              newStats.bitrate = Math.round((bytesDelta * 8) / timeDelta / 1000); // kbps
            }
          }

          // Update prev stats for next calculation
          if (newStats.bytesReceived !== undefined && newStats.framesReceived !== undefined) {
            prevStatsRef.current = {
              timestamp: Date.now(),
              bytesReceived: newStats.bytesReceived,
              framesReceived: newStats.framesReceived,
            };
          }
        }

        // Track (for resolution)
        if (stat.type === 'track' && stat.kind === 'video') {
          newStats.width = stat.frameWidth || 0;
          newStats.height = stat.frameHeight || 0;
        }

        // Candidate pair (for latency)
        if (stat.type === 'candidate-pair' && stat.state === 'succeeded') {
          newStats.latency = stat.currentRoundTripTime
            ? Math.round(stat.currentRoundTripTime * 1000)
            : 0;
        }
      });

      // Calculate quality score
      const { quality, qualityLabel } = calculateQuality(newStats);

      setStats((prev) => ({
        ...prev,
        ...newStats,
        quality,
        qualityLabel,
      }));
    } catch (err) {
      console.error('Error collecting stats:', err);
    }
  }, [peerConnection]);

  useEffect(() => {
    if (!enabled || !peerConnection) {
      setStats(DEFAULT_STATS);
      prevStatsRef.current = null;
      return;
    }

    // Initial collection
    collectStats();

    // Set up interval
    const intervalId = setInterval(collectStats, intervalMs);

    return () => {
      clearInterval(intervalId);
    };
  }, [enabled, peerConnection, collectStats, intervalMs]);

  // Reset stats when connection changes
  useEffect(() => {
    if (!peerConnection) {
      setStats(DEFAULT_STATS);
      prevStatsRef.current = null;
    }
  }, [peerConnection]);

  return stats;
}

"""
WebRTC client for streaming screen capture to web browsers.

Uses aiortc for WebRTC implementation with custom video track
that streams screen captures.
"""

import asyncio
import json
import logging
from typing import Dict, Callable, Optional, Any

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc import VideoStreamTrack
from av import VideoFrame

from screen_capture import ScreenCapture

logger = logging.getLogger(__name__)


class ScreenTrack(VideoStreamTrack):
    """
    Custom video track that streams screen capture frames.

    Inherits from VideoStreamTrack which provides:
    - kind = "video"
    - next_timestamp() for frame timing
    - readyState property
    """

    kind = "video"

    def __init__(self, screen_capture: ScreenCapture):
        """
        Initialize the screen track.

        Args:
            screen_capture: ScreenCapture instance for grabbing frames
        """
        super().__init__()
        self._screen_capture = screen_capture
        self._frame_count = 0

    async def recv(self) -> VideoFrame:
        """
        Receive the next video frame from screen capture.

        Returns:
            VideoFrame object containing the captured screen
        """
        # Get timing from parent's next_timestamp (handles frame pacing)
        pts, time_base = await self.next_timestamp()

        # Capture frame as PIL Image
        pil_image = self._screen_capture.capture_frame()

        # Convert PIL Image to numpy array (RGB format)
        frame_array = np.array(pil_image)

        # Create VideoFrame from numpy array
        frame = VideoFrame.from_ndarray(frame_array, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base

        self._frame_count += 1
        return frame

    def stop(self):
        """Stop the track."""
        super().stop()
        logger.debug(f"ScreenTrack stopped after {self._frame_count} frames")


class WebRTCClient:
    """
    Manages WebRTC peer connections for screen streaming.

    Handles:
    - Multiple client connections (one RTCPeerConnection per client)
    - SDP offer/answer negotiation
    - ICE candidate exchange
    - Data channel for input commands (placeholder for Step 9)
    """

    def __init__(
        self,
        screen_capture: ScreenCapture,
        send_answer: Callable[[str, str], Any],
        send_ice_candidate: Callable[[str, dict], Any],
    ):
        """
        Initialize WebRTC client.

        Args:
            screen_capture: ScreenCapture instance for video
            send_answer: Async callback to send SDP answer via signaling
            send_ice_candidate: Async callback to send ICE candidate via signaling
        """
        self._screen_capture = screen_capture
        self._send_answer = send_answer
        self._send_ice_candidate = send_ice_candidate

        # Active peer connections: client_id -> RTCPeerConnection
        self._peer_connections: Dict[str, RTCPeerConnection] = {}

        # Screen tracks per connection (each client gets its own track)
        self._tracks: Dict[str, ScreenTrack] = {}

        # Data channels for input: client_id -> RTCDataChannel
        self._data_channels: Dict[str, Any] = {}

        # Input handler callback (set in Step 9)
        self._on_input: Optional[Callable[[str, dict], None]] = None

        logger.info("WebRTC client initialized")

    def set_input_handler(self, handler: Callable[[str, dict], None]):
        """Set callback for handling input from data channels."""
        self._on_input = handler

    async def handle_offer(self, client_id: str, sdp: str):
        """
        Handle incoming SDP offer from a client.

        Args:
            client_id: The connection ID of the client
            sdp: The SDP offer string
        """
        logger.info(f"Processing offer from client: {client_id}")

        try:
            # Create new peer connection for this client with STUN servers
            pc = RTCPeerConnection(configuration={
                "iceServers": [
                    {"urls": "stun:stun.l.google.com:19302"},
                    {"urls": "stun:stun1.l.google.com:19302"},
                ]
            })
            self._peer_connections[client_id] = pc

            # Set up ICE candidate callback
            @pc.on("icecandidate")
            async def on_icecandidate(candidate):
                if candidate:
                    logger.debug(f"Sending ICE candidate to {client_id}")
                    await self._send_ice_candidate(client_id, {
                        "candidate": candidate.candidate,
                        "sdpMid": candidate.sdpMid,
                        "sdpMLineIndex": candidate.sdpMLineIndex,
                    })

            # Set up connection state monitoring
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"Connection state ({client_id}): {pc.connectionState}")
                if pc.connectionState in ("failed", "closed"):
                    await self._cleanup_connection(client_id)

            # Set up ICE connection state monitoring
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logger.debug(f"ICE connection state ({client_id}): {pc.iceConnectionState}")

            # Set up data channel handling (for Step 9 input injection)
            @pc.on("datachannel")
            def on_datachannel(channel):
                logger.info(f"Data channel opened: {channel.label}")
                self._data_channels[client_id] = channel

                @channel.on("message")
                def on_message(message):
                    self._handle_data_message(client_id, message)

            # Create and add screen track
            track = ScreenTrack(self._screen_capture)
            self._tracks[client_id] = track
            pc.addTrack(track)
            logger.debug(f"Added video track for {client_id}")

            # Set remote description (the offer)
            offer = RTCSessionDescription(sdp=sdp, type="offer")
            await pc.setRemoteDescription(offer)

            # Create and set local description (the answer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Send answer back to client
            await self._send_answer(client_id, pc.localDescription.sdp)
            logger.info(f"Sent answer to client: {client_id}")

        except Exception as e:
            logger.error(f"Error handling offer from {client_id}: {e}")
            await self._cleanup_connection(client_id)
            raise

    async def handle_ice_candidate(self, client_id: str, candidate: dict):
        """
        Handle incoming ICE candidate from a client.

        Args:
            client_id: The connection ID of the client
            candidate: ICE candidate dictionary with 'candidate', 'sdpMid', 'sdpMLineIndex'
        """
        pc = self._peer_connections.get(client_id)
        if not pc:
            logger.warning(f"No peer connection for client: {client_id}")
            return

        try:
            # Handle null/empty candidate (end-of-candidates signal)
            candidate_str = candidate.get("candidate")
            if not candidate_str:
                logger.debug(f"Received end-of-candidates signal from {client_id}")
                return

            # Parse and add the ICE candidate
            ice_candidate = RTCIceCandidate(
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                candidate=candidate_str,
            )
            await pc.addIceCandidate(ice_candidate)
            logger.debug(f"Added ICE candidate for {client_id}")

        except Exception as e:
            logger.error(f"Error adding ICE candidate for {client_id}: {e}")

    def _handle_data_message(self, client_id: str, message: str):
        """
        Handle incoming message from data channel.

        Args:
            client_id: The client ID
            message: JSON string containing input command
        """
        # Placeholder for Step 9 input handling
        if self._on_input:
            try:
                data = json.loads(message)
                self._on_input(client_id, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {client_id}: {message}")
        else:
            logger.debug(f"Data message from {client_id} (no handler): {message[:100]}")

    async def _cleanup_connection(self, client_id: str):
        """
        Clean up resources for a disconnected client.

        Args:
            client_id: The client ID to clean up
        """
        logger.info(f"Cleaning up connection: {client_id}")

        # Stop and remove track
        track = self._tracks.pop(client_id, None)
        if track:
            track.stop()

        # Remove data channel
        self._data_channels.pop(client_id, None)

        # Close and remove peer connection
        pc = self._peer_connections.pop(client_id, None)
        if pc:
            await pc.close()

    async def close_all(self):
        """Close all peer connections and clean up."""
        logger.info("Closing all WebRTC connections")
        client_ids = list(self._peer_connections.keys())
        for client_id in client_ids:
            await self._cleanup_connection(client_id)
        logger.info("All WebRTC connections closed")

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._peer_connections)

    def get_connection_stats(self) -> dict:
        """Get statistics about active connections."""
        return {
            "active_connections": self.connection_count,
            "client_ids": list(self._peer_connections.keys()),
        }

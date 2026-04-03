import asyncio
import json
import logging
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from config import Config, RECONNECT_DELAY, MAX_RECONNECT_ATTEMPTS

logger = logging.getLogger(__name__)


class SignalingClient:
    """WebSocket client for signaling server communication."""

    def __init__(self, config: Config):
        self.config = config
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connection_id: Optional[str] = None
        self.is_registered: bool = False
        self._running: bool = False
        self._reconnect_count: int = 0

        # Message handlers
        self._on_offer: Optional[Callable] = None
        self._on_ice_candidate: Optional[Callable] = None

    def on_offer(self, handler: Callable):
        """Set handler for incoming SDP offers."""
        self._on_offer = handler

    def on_ice_candidate(self, handler: Callable):
        """Set handler for incoming ICE candidates."""
        self._on_ice_candidate = handler

    async def connect(self) -> bool:
        """Connect to the signaling server."""
        try:
            logger.info(f"Connecting to {self.config.server_url}...")
            self.websocket = await websockets.connect(self.config.server_url)

            # Wait for connection confirmation
            msg = await self.websocket.recv()
            data = json.loads(msg)

            if data.get("type") == "connected":
                self.connection_id = data.get("connection_id")
                logger.info(f"Connected with ID: {self.connection_id}")
                self._reconnect_count = 0
                return True
            else:
                logger.error(f"Unexpected response: {data}")
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def register(self) -> bool:
        """Register as an agent with the server."""
        if not self.websocket:
            logger.error("Not connected")
            return False

        try:
            # Build registration message
            register_msg = {
                "type": "register",
                "agent_id": self.config.agent_id,
                "password": self.config.password,
            }
            # Include token if provided
            if self.config.agent_token:
                register_msg["token"] = self.config.agent_token

            # Send registration message
            await self.websocket.send(json.dumps(register_msg))

            # Wait for response
            msg = await self.websocket.recv()
            data = json.loads(msg)

            if data.get("type") == "registered":
                self.is_registered = True
                logger.info(f"Registered as agent: {self.config.agent_id}")
                return True
            else:
                logger.error(f"Registration failed: {data.get('message', 'Unknown error')}")
                return False

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False

    async def send_answer(self, target: str, sdp: str):
        """Send SDP answer to a client."""
        if not self.websocket:
            return

        await self.websocket.send(json.dumps({
            "type": "answer",
            "sdp": sdp,
            "target": target,
        }))
        logger.debug(f"Sent answer to {target}")

    async def send_ice_candidate(self, target: str, candidate: dict):
        """Send ICE candidate to a client."""
        if not self.websocket:
            return

        await self.websocket.send(json.dumps({
            "type": "ice-candidate",
            "candidate": candidate,
            "target": target,
        }))
        logger.debug(f"Sent ICE candidate to {target}")

    async def _handle_message(self, data: dict):
        """Handle incoming message from server."""
        msg_type = data.get("type")

        if msg_type == "offer":
            # Incoming WebRTC offer from client
            logger.info(f"Received offer from {data.get('from')}")
            if self._on_offer:
                await self._on_offer(data.get("from"), data.get("sdp"))

        elif msg_type == "ice-candidate":
            # Incoming ICE candidate
            logger.debug(f"Received ICE candidate from {data.get('from')}")
            if self._on_ice_candidate:
                await self._on_ice_candidate(data.get("from"), data.get("candidate"))

        elif msg_type == "error":
            logger.error(f"Server error: {data.get('message')}")

        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def listen(self):
        """Listen for incoming messages."""
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)

        except ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}")
        except Exception as e:
            logger.error(f"Error in message loop: {e}")

    async def run(self):
        """Main run loop with reconnection support."""
        self._running = True

        while self._running:
            # Connect
            if await self.connect():
                # Register
                if await self.register():
                    # Listen for messages
                    await self.listen()

            # Connection lost or failed
            self.is_registered = False
            self.websocket = None

            if not self._running:
                break

            # Reconnect logic
            self._reconnect_count += 1
            if MAX_RECONNECT_ATTEMPTS > 0 and self._reconnect_count >= MAX_RECONNECT_ATTEMPTS:
                logger.error(f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) reached")
                break

            logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds... (attempt {self._reconnect_count})")
            await asyncio.sleep(RECONNECT_DELAY)

    async def stop(self):
        """Stop the signaling client."""
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        logger.info("Signaling client stopped")

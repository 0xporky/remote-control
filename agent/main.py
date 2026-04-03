import asyncio
import logging
import signal
import sys

from config import Config
from signaling import SignalingClient
from screen_capture import ScreenCapture
from webrtc_client import WebRTCClient
from input_handler import InputHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Agent:
    """Remote control agent."""

    def __init__(self, config: Config):
        self.config = config
        self.signaling = SignalingClient(config)
        self._running = False

        # Initialize screen capture with config settings
        self.screen_capture = ScreenCapture(
            monitor=config.monitor,
            scale=config.scale,
            fps=config.fps,
        )

        # Initialize WebRTC client with signaling callbacks
        self.webrtc = WebRTCClient(
            screen_capture=self.screen_capture,
            send_answer=self.signaling.send_answer,
            send_ice_candidate=self.signaling.send_ice_candidate,
        )

        # Initialize input handler for mouse/keyboard injection
        self.input_handler = InputHandler()

        # Connect input handler to WebRTC client
        self.webrtc.set_input_handler(self.input_handler.handle_input)

        # Set up message handlers
        self.signaling.on_offer(self._handle_offer)
        self.signaling.on_ice_candidate(self._handle_ice_candidate)

    async def _handle_offer(self, client_id: str, sdp: str):
        """Handle incoming WebRTC offer from a client."""
        logger.info(f"Received offer from client: {client_id}")
        await self.webrtc.handle_offer(client_id, sdp)

    async def _handle_ice_candidate(self, client_id: str, candidate: dict):
        """Handle incoming ICE candidate from a client."""
        logger.debug(f"Received ICE candidate from client: {client_id}")
        await self.webrtc.handle_ice_candidate(client_id, candidate)

    async def run(self):
        """Run the agent."""
        self._running = True
        logger.info(f"Starting agent: {self.config.agent_id}")
        logger.info(f"Server: {self.config.server_url}")
        logger.info(f"Screen: monitor={self.config.monitor}, "
                   f"scale={self.config.scale}, fps={self.config.fps}")

        try:
            await self.signaling.run()
        except asyncio.CancelledError:
            logger.info("Agent cancelled")
        finally:
            await self.stop()

    async def stop(self):
        """Stop the agent."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping agent...")

        # Close input handler
        self.input_handler.close()

        # Close WebRTC connections
        await self.webrtc.close_all()

        # Close screen capture
        self.screen_capture.close()

        # Close signaling
        await self.signaling.stop()

        logger.info("Agent stopped")


async def main():
    """Main entry point."""
    # Parse config from command line
    config = Config.from_args()

    # Create agent
    agent = Agent(config)

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(agent.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handlers not available on Windows
            pass

    # Run agent
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)

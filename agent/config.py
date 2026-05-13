import argparse
import os
import socket
from typing import Optional

# Default settings
DEFAULT_SERVER_URL: str = os.getenv("SERVER_URL", "ws://localhost:8000/ws/signaling")
DEFAULT_AGENT_ID: str = os.getenv("AGENT_ID", socket.gethostname())
DEFAULT_AGENT_TOKEN: Optional[str] = os.getenv("AGENT_TOKEN")  # Authorization token (required)

# Reconnection settings
RECONNECT_DELAY: int = 5  # seconds
MAX_RECONNECT_ATTEMPTS: int = 0  # 0 = unlimited

# Screen capture settings
DEFAULT_MONITOR: int = 1  # Primary monitor
DEFAULT_FPS: int = 30
DEFAULT_SCALE: float = 1.0


class Config:
    """Agent configuration."""

    def __init__(
        self,
        server_url: str = DEFAULT_SERVER_URL,
        agent_id: str = DEFAULT_AGENT_ID,
        agent_token: Optional[str] = DEFAULT_AGENT_TOKEN,
        monitor: int = DEFAULT_MONITOR,
        fps: int = DEFAULT_FPS,
        scale: float = DEFAULT_SCALE,
    ):
        self.server_url = server_url
        self.agent_id = agent_id
        self.agent_token = agent_token
        self.monitor = monitor
        self.fps = fps
        self.scale = scale

    @classmethod
    def from_args(cls) -> "Config":
        """Create config from command line arguments."""
        parser = argparse.ArgumentParser(
            description="Remote Control Agent - Windows remote desktop agent"
        )
        parser.add_argument(
            "--server", "-s",
            default=DEFAULT_SERVER_URL,
            help=f"Server WebSocket URL (default: {DEFAULT_SERVER_URL})"
        )
        parser.add_argument(
            "--agent-id", "-i",
            default=DEFAULT_AGENT_ID,
            help=f"Agent ID (default: {DEFAULT_AGENT_ID})"
        )
        parser.add_argument(
            "--token", "-t",
            default=DEFAULT_AGENT_TOKEN,
            help="Agent authorization token (required; or set AGENT_TOKEN env var)"
        )
        parser.add_argument(
            "--monitor", "-m",
            type=int,
            default=DEFAULT_MONITOR,
            help=f"Monitor number to capture (default: {DEFAULT_MONITOR})"
        )
        parser.add_argument(
            "--fps", "-f",
            type=int,
            default=DEFAULT_FPS,
            help=f"Target FPS (default: {DEFAULT_FPS})"
        )
        parser.add_argument(
            "--scale",
            type=float,
            default=DEFAULT_SCALE,
            help=f"Scale factor for resolution (default: {DEFAULT_SCALE})"
        )

        args = parser.parse_args()

        if not args.token:
            raise SystemExit("--token (or AGENT_TOKEN env var) is required")

        return cls(
            server_url=args.server,
            agent_id=args.agent_id,
            agent_token=args.token,
            monitor=args.monitor,
            fps=args.fps,
            scale=args.scale,
        )

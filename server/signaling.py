import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a WebSocket connection (agent or client)."""
    websocket: WebSocket
    connection_id: str
    is_agent: bool = False
    agent_id: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections for WebRTC signaling."""

    def __init__(self):
        # All active connections: connection_id -> Connection
        self._connections: dict[str, Connection] = {}
        # Registered agents: agent_id -> connection_id
        self._agents: dict[str, str] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, connection_id: str) -> Connection:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        connection = Connection(websocket=websocket, connection_id=connection_id)
        async with self._lock:
            self._connections[connection_id] = connection
        logger.info(f"Connection established: {connection_id}")
        return connection

    async def disconnect(self, connection_id: str):
        """Remove a connection and clean up."""
        async with self._lock:
            connection = self._connections.pop(connection_id, None)
            if connection and connection.is_agent and connection.agent_id:
                self._agents.pop(connection.agent_id, None)
                logger.info(f"Agent unregistered: {connection.agent_id}")
        logger.info(f"Connection closed: {connection_id}")

    async def register_agent(self, connection_id: str, agent_id: str) -> bool:
        """Register a connection as an agent."""
        async with self._lock:
            if agent_id in self._agents:
                logger.warning(f"Agent already registered: {agent_id}")
                return False

            connection = self._connections.get(connection_id)
            if not connection:
                return False

            connection.is_agent = True
            connection.agent_id = agent_id
            self._agents[agent_id] = connection_id
            logger.info(f"Agent registered: {agent_id} (connection: {connection_id})")
            return True

    async def get_agent_list(self) -> list[str]:
        """Get list of registered agent IDs."""
        async with self._lock:
            return list(self._agents.keys())

    async def get_connection(self, connection_id: str) -> Optional[Connection]:
        """Get a connection by ID."""
        async with self._lock:
            return self._connections.get(connection_id)

    async def get_agent_connection(self, agent_id: str) -> Optional[Connection]:
        """Get an agent's connection by agent ID."""
        async with self._lock:
            connection_id = self._agents.get(agent_id)
            if connection_id:
                return self._connections.get(connection_id)
            return None

    async def send_to_connection(self, connection_id: str, message: dict) -> bool:
        """Send a message to a specific connection."""
        connection = await self.get_connection(connection_id)
        if connection:
            try:
                await connection.websocket.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send to {connection_id}: {e}")
        return False

    async def send_to_agent(self, agent_id: str, message: dict) -> bool:
        """Send a message to a specific agent."""
        connection = await self.get_agent_connection(agent_id)
        if connection:
            try:
                await connection.websocket.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send to agent {agent_id}: {e}")
        return False

    async def relay_message(self, from_id: str, target_id: str, message: dict) -> bool:
        """Relay a message from one connection to another."""
        # Add sender info to the message
        message["from"] = from_id

        # Try to find target as agent first, then as connection
        connection = await self.get_agent_connection(target_id)
        if not connection:
            connection = await self.get_connection(target_id)

        if connection:
            try:
                await connection.websocket.send_json(message)
                logger.debug(f"Relayed message from {from_id} to {target_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to relay to {target_id}: {e}")
        else:
            logger.warning(f"Target not found: {target_id}")
        return False


# Global connection manager instance
manager = ConnectionManager()

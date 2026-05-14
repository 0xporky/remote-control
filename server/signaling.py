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
        """Register a connection as an agent. Evicts any prior registration with the same agent_id."""
        stale_ws = None
        async with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return False

            prior_connection_id = self._agents.get(agent_id)
            if prior_connection_id and prior_connection_id != connection_id:
                prior = self._connections.get(prior_connection_id)
                if prior is not None:
                    stale_ws = prior.websocket
                    prior.is_agent = False
                    prior.agent_id = None
                logger.info(f"Evicting prior registration for {agent_id} (connection: {prior_connection_id})")

            connection.is_agent = True
            connection.agent_id = agent_id
            self._agents[agent_id] = connection_id
            logger.info(f"Agent registered: {agent_id} (connection: {connection_id})")

        if stale_ws is not None:
            try:
                await stale_ws.close(code=1000, reason="Superseded by new registration")
            except Exception as e:
                logger.warning(f"Failed to close stale agent connection: {e}")
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
        """Relay a message from one connection to another.

        ``from`` is set to the sender's agent_id when the sender is a registered
        agent, otherwise to the raw connection_id. This lets browser clients
        track the peer by a stable identifier across reconnects.
        """
        async with self._lock:
            sender = self._connections.get(from_id)
            from_value = sender.agent_id if sender and sender.is_agent and sender.agent_id else from_id
        message["from"] = from_value

        # Try to find target as agent first, then as connection
        connection = await self.get_agent_connection(target_id)
        if not connection:
            connection = await self.get_connection(target_id)

        if connection:
            try:
                await connection.websocket.send_json(message)
                logger.debug(f"Relayed message from {from_value} to {target_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to relay to {target_id}: {e}")
        else:
            logger.warning(f"Target not found: {target_id}")
        return False


# Global connection manager instance
manager = ConnectionManager()

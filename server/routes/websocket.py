import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import config
from auth import verify_token
from signaling import manager
from messages import validate_message, RegisterMessage, AuthenticateMessage

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionManager:
    """Manages WebSocket session state and timeouts."""

    def __init__(self, websocket: WebSocket, connection_id: str):
        self.websocket = websocket
        self.connection_id = connection_id
        self.authenticated = False
        self.is_agent = False
        self.created_at = time.time()
        self.last_activity = time.time()
        self._timeout_task = None

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return (time.time() - self.last_activity) > config.WS_SESSION_TIMEOUT_SECONDS

    async def start_timeout_monitor(self, on_timeout):
        """Start monitoring for session timeout."""
        async def monitor():
            while True:
                await asyncio.sleep(config.WS_PING_INTERVAL_SECONDS)
                if self.is_expired():
                    logger.info(f"Session timeout for {self.connection_id}")
                    await on_timeout()
                    break

        self._timeout_task = asyncio.create_task(monitor())

    def stop_timeout_monitor(self):
        """Stop the timeout monitor."""
        if self._timeout_task:
            self._timeout_task.cancel()


@router.websocket("/ws/signaling")
async def websocket_signaling(websocket: WebSocket):
    """
    WebSocket endpoint for WebRTC signaling.

    Clients must authenticate with a JWT token first.
    Agents must register with password and optional agent token.

    Message types:
    - authenticate: Client JWT auth {"type": "authenticate", "token": "..."}
    - register: Agent registration {"type": "register", "agent_id": "...", "password": "...", "token": "..."}
    - offer: SDP offer {"type": "offer", "sdp": "...", "target": "agent_id"}
    - answer: SDP answer {"type": "answer", "sdp": "...", "target": "client_id"}
    - ice-candidate: ICE candidate {"type": "ice-candidate", "candidate": {...}, "target": "..."}
    - get-agents: List agents {"type": "get-agents"}
    """
    # Generate unique connection ID
    connection_id = str(uuid.uuid4())

    # Accept connection
    connection = await manager.connect(websocket, connection_id)

    # Create session manager
    session = SessionManager(websocket, connection_id)

    # Send connection ID to client
    await websocket.send_json({
        "type": "connected",
        "connection_id": connection_id,
    })

    async def handle_timeout():
        """Handle session timeout."""
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Session timeout",
            })
            await websocket.close(code=1000, reason="Session timeout")
        except Exception:
            pass

    # Start timeout monitor
    await session.start_timeout_monitor(handle_timeout)

    try:
        while True:
            # Receive message
            try:
                data = await websocket.receive_json()
            except Exception as e:
                logger.warning(f"Invalid JSON from {connection_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            # Update activity
            session.update_activity()

            # Validate message
            is_valid, parsed_msg, error = validate_message(data)
            if not is_valid:
                await websocket.send_json({
                    "type": "error",
                    "message": error,
                })
                continue

            msg_type = data.get("type")

            # Handle authentication (clients)
            if msg_type == "authenticate":
                auth_msg: AuthenticateMessage = parsed_msg
                token_data = verify_token(auth_msg.token)

                if token_data is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid or expired token",
                    })
                    continue

                session.authenticated = True
                await websocket.send_json({
                    "type": "authenticated",
                    "client_id": connection_id,
                })
                logger.info(f"Client authenticated: {connection_id}")
                continue

            # Handle agent registration
            if msg_type == "register":
                reg_msg: RegisterMessage = parsed_msg
                agent_id = reg_msg.agent_id
                password = reg_msg.password
                agent_token = reg_msg.token

                # Verify password
                if password != config.AUTH_PASSWORD:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid password",
                    })
                    continue

                # Verify agent token if required
                if not config.is_valid_agent_token(agent_token):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid or missing agent token",
                    })
                    logger.warning(f"Agent registration rejected - invalid token: {agent_id}")
                    continue

                # Register agent
                success = await manager.register_agent(connection_id, agent_id)
                if success:
                    session.authenticated = True
                    session.is_agent = True

                await websocket.send_json({
                    "type": "registered" if success else "error",
                    "agent_id": agent_id,
                    "message": "Agent registered" if success else "Agent ID already in use",
                })
                continue

            # All other messages require authentication
            if not session.authenticated:
                await websocket.send_json({
                    "type": "error",
                    "message": "Not authenticated",
                })
                continue

            if msg_type == "get-agents":
                # List available agents
                agents = await manager.get_agent_list()
                await websocket.send_json({
                    "type": "agents-list",
                    "agents": agents,
                })

            elif msg_type == "offer":
                # Relay SDP offer to target agent
                target = data.get("target")

                success = await manager.relay_message(connection_id, target, {
                    "type": "offer",
                    "sdp": data.get("sdp"),
                })
                if not success:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Agent not found: {target}",
                    })

            elif msg_type == "answer":
                # Relay SDP answer to target client
                target = data.get("target")

                success = await manager.relay_message(connection_id, target, {
                    "type": "answer",
                    "sdp": data.get("sdp"),
                })
                if not success:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Client not found: {target}",
                    })

            elif msg_type == "ice-candidate":
                # Relay ICE candidate
                target = data.get("target")
                candidate = data.get("candidate")

                await manager.relay_message(connection_id, target, {
                    "type": "ice-candidate",
                    "candidate": candidate,
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        session.stop_timeout_monitor()
        await manager.disconnect(connection_id)

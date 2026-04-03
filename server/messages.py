"""
WebSocket message validation using Pydantic.

Defines and validates all message types for WebRTC signaling.
"""

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


class BaseMessage(BaseModel):
    """Base class for all WebSocket messages."""
    type: str


class RegisterMessage(BaseModel):
    """Agent registration message."""
    type: Literal["register"]
    agent_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    token: Optional[str] = Field(None, max_length=256)  # Agent authorization token

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        # Allow alphanumeric, hyphens, and underscores
        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("agent_id must contain only alphanumeric characters, hyphens, and underscores")
        return v


class AuthenticateMessage(BaseModel):
    """Client authentication message."""
    type: Literal["authenticate"]
    token: str = Field(..., min_length=1, max_length=2048)


class GetAgentsMessage(BaseModel):
    """Request agent list message."""
    type: Literal["get-agents"]


class ConnectMessage(BaseModel):
    """Client connect to agent message."""
    type: Literal["connect"]
    target: str = Field(..., min_length=1, max_length=64)


class OfferMessage(BaseModel):
    """SDP offer message."""
    type: Literal["offer"]
    sdp: str = Field(..., min_length=1, max_length=65536)
    target: str = Field(..., min_length=1, max_length=64)


class AnswerMessage(BaseModel):
    """SDP answer message."""
    type: Literal["answer"]
    sdp: str = Field(..., min_length=1, max_length=65536)
    target: str = Field(..., min_length=1, max_length=64)


class IceCandidateData(BaseModel):
    """ICE candidate data."""
    candidate: Optional[str] = Field(None, max_length=2048)
    sdpMid: Optional[str] = Field(None, max_length=64)
    sdpMLineIndex: Optional[int] = Field(None, ge=0, le=255)


class IceCandidateMessage(BaseModel):
    """ICE candidate message."""
    type: Literal["ice-candidate"]
    candidate: Optional[IceCandidateData] = None
    target: str = Field(..., min_length=1, max_length=64)


# Union type for all valid incoming messages
IncomingMessage = Union[
    RegisterMessage,
    AuthenticateMessage,
    GetAgentsMessage,
    ConnectMessage,
    OfferMessage,
    AnswerMessage,
    IceCandidateMessage,
]


def validate_message(data: dict) -> tuple[bool, Optional[BaseModel], str]:
    """
    Validate an incoming WebSocket message.

    Args:
        data: Raw message dictionary

    Returns:
        Tuple of (is_valid, parsed_message, error_message)
    """
    msg_type = data.get("type")

    if not msg_type:
        return False, None, "Missing message type"

    try:
        if msg_type == "register":
            return True, RegisterMessage(**data), ""
        elif msg_type == "authenticate":
            return True, AuthenticateMessage(**data), ""
        elif msg_type == "get-agents":
            return True, GetAgentsMessage(**data), ""
        elif msg_type == "connect":
            return True, ConnectMessage(**data), ""
        elif msg_type == "offer":
            return True, OfferMessage(**data), ""
        elif msg_type == "answer":
            return True, AnswerMessage(**data), ""
        elif msg_type == "ice-candidate":
            return True, IceCandidateMessage(**data), ""
        else:
            return False, None, f"Unknown message type: {msg_type}"
    except Exception as e:
        return False, None, f"Validation error: {str(e)}"


# Input event validation for data channel messages
class MouseMoveEvent(BaseModel):
    """Mouse move input event."""
    type: Literal["mousemove"]
    dx: int = Field(..., ge=-10000, le=10000)
    dy: int = Field(..., ge=-10000, le=10000)


class MouseButtonEvent(BaseModel):
    """Mouse button input event."""
    type: Literal["mousedown", "mouseup"]
    button: int = Field(..., ge=0, le=4)


class WheelEvent(BaseModel):
    """Mouse wheel input event."""
    type: Literal["wheel"]
    deltaX: int = Field(..., ge=-10000, le=10000)
    deltaY: int = Field(..., ge=-10000, le=10000)


class KeyEvent(BaseModel):
    """Keyboard input event."""
    type: Literal["keydown", "keyup"]
    key: str = Field(..., min_length=1, max_length=32)
    code: str = Field(..., min_length=1, max_length=32)


InputEvent = Union[MouseMoveEvent, MouseButtonEvent, WheelEvent, KeyEvent]


def validate_input_event(data: dict) -> tuple[bool, Optional[BaseModel], str]:
    """
    Validate an input event from the data channel.

    Args:
        data: Raw event dictionary

    Returns:
        Tuple of (is_valid, parsed_event, error_message)
    """
    event_type = data.get("type")

    if not event_type:
        return False, None, "Missing event type"

    try:
        if event_type == "mousemove":
            return True, MouseMoveEvent(**data), ""
        elif event_type in ("mousedown", "mouseup"):
            return True, MouseButtonEvent(**data), ""
        elif event_type == "wheel":
            return True, WheelEvent(**data), ""
        elif event_type in ("keydown", "keyup"):
            return True, KeyEvent(**data), ""
        else:
            return False, None, f"Unknown event type: {event_type}"
    except Exception as e:
        return False, None, f"Validation error: {str(e)}"

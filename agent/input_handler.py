"""
Input handler for injecting mouse and keyboard events on Windows.

Uses pynput library to simulate user input based on commands
received from the web client via WebRTC data channel.
"""

import logging
from typing import Dict, Any, Optional

from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

logger = logging.getLogger(__name__)


# Map mouse button numbers to pynput Button
MOUSE_BUTTON_MAP = {
    0: Button.left,
    1: Button.middle,
    2: Button.right,
}

# Map browser key codes to pynput Key
# This maps common special keys from browser KeyboardEvent.key values
SPECIAL_KEY_MAP = {
    # Modifier keys
    "Shift": Key.shift,
    "Control": Key.ctrl,
    "Alt": Key.alt,
    "Meta": Key.cmd,  # Windows key / Command key

    # Navigation keys
    "ArrowUp": Key.up,
    "ArrowDown": Key.down,
    "ArrowLeft": Key.left,
    "ArrowRight": Key.right,
    "Home": Key.home,
    "End": Key.end,
    "PageUp": Key.page_up,
    "PageDown": Key.page_down,

    # Editing keys
    "Backspace": Key.backspace,
    "Delete": Key.delete,
    "Enter": Key.enter,
    "Tab": Key.tab,
    "Insert": Key.insert,

    # Function keys
    "F1": Key.f1,
    "F2": Key.f2,
    "F3": Key.f3,
    "F4": Key.f4,
    "F5": Key.f5,
    "F6": Key.f6,
    "F7": Key.f7,
    "F8": Key.f8,
    "F9": Key.f9,
    "F10": Key.f10,
    "F11": Key.f11,
    "F12": Key.f12,

    # Other special keys
    "Escape": Key.esc,
    "CapsLock": Key.caps_lock,
    "NumLock": Key.num_lock,
    "ScrollLock": Key.scroll_lock,
    "Pause": Key.pause,
    "PrintScreen": Key.print_screen,
    " ": Key.space,
}


class InputHandler:
    """
    Handles input injection for remote control.

    Receives input events from the web client and translates them
    to actual mouse/keyboard actions using pynput.
    """

    def __init__(self):
        """Initialize input controllers."""
        self._mouse = MouseController()
        self._keyboard = KeyboardController()
        self._enabled = True

        # Track pressed keys to handle key release properly
        self._pressed_keys: set = set()

        logger.info("Input handler initialized")

    @property
    def enabled(self) -> bool:
        """Check if input handling is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        """Enable or disable input handling."""
        self._enabled = value
        if not value:
            # Release all pressed keys when disabled
            self._release_all_keys()
        logger.info(f"Input handling {'enabled' if value else 'disabled'}")

    def handle_input(self, client_id: str, event: Dict[str, Any]):
        """
        Handle an input event from a client.

        Args:
            client_id: The client ID sending the event
            event: Input event dictionary with 'type' and event-specific data
        """
        if not self._enabled:
            return

        event_type = event.get("type")

        try:
            if event_type == "mousemove":
                self._handle_mouse_move(event)
            elif event_type == "mousedown":
                self._handle_mouse_down(event)
            elif event_type == "mouseup":
                self._handle_mouse_up(event)
            elif event_type == "wheel":
                self._handle_wheel(event)
            elif event_type == "keydown":
                self._handle_key_down(event)
            elif event_type == "keyup":
                self._handle_key_up(event)
            else:
                logger.warning(f"Unknown input event type: {event_type}")
        except Exception as e:
            logger.error(f"Error handling input event {event_type}: {e}")

    def _handle_mouse_move(self, event: Dict[str, Any]):
        """Handle relative mouse movement."""
        dx = event.get("dx", 0)
        dy = event.get("dy", 0)

        if dx != 0 or dy != 0:
            self._mouse.move(dx, dy)

    def _handle_mouse_down(self, event: Dict[str, Any]):
        """Handle mouse button press."""
        button_num = event.get("button", 0)
        button = MOUSE_BUTTON_MAP.get(button_num)

        if button:
            self._mouse.press(button)
        else:
            logger.warning(f"Unknown mouse button: {button_num}")

    def _handle_mouse_up(self, event: Dict[str, Any]):
        """Handle mouse button release."""
        button_num = event.get("button", 0)
        button = MOUSE_BUTTON_MAP.get(button_num)

        if button:
            self._mouse.release(button)
        else:
            logger.warning(f"Unknown mouse button: {button_num}")

    def _handle_wheel(self, event: Dict[str, Any]):
        """Handle mouse wheel scroll."""
        delta_x = event.get("deltaX", 0)
        delta_y = event.get("deltaY", 0)

        # pynput scroll uses clicks, normalize delta values
        # Typical delta is ~100 per "click" in browsers
        scroll_x = -int(delta_x / 100) if delta_x else 0
        scroll_y = -int(delta_y / 100) if delta_y else 0

        if scroll_x != 0 or scroll_y != 0:
            self._mouse.scroll(scroll_x, scroll_y)

    def _handle_key_down(self, event: Dict[str, Any]):
        """Handle key press."""
        key = self._map_key(event)
        if key is None:
            return

        # Track the key as pressed
        key_id = event.get("code", event.get("key", ""))
        self._pressed_keys.add(key_id)

        self._keyboard.press(key)

    def _handle_key_up(self, event: Dict[str, Any]):
        """Handle key release."""
        key = self._map_key(event)
        if key is None:
            return

        # Remove from pressed keys
        key_id = event.get("code", event.get("key", ""))
        self._pressed_keys.discard(key_id)

        self._keyboard.release(key)

    def _map_key(self, event: Dict[str, Any]) -> Optional[Any]:
        """
        Map a browser key event to a pynput key.

        Args:
            event: Key event with 'key' and 'code' fields

        Returns:
            pynput Key or character string, or None if unmappable
        """
        key_value = event.get("key", "")

        # Check if it's a special key
        if key_value in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key_value]

        # For single character keys, use the character directly
        if len(key_value) == 1:
            return key_value

        # Handle some edge cases
        if key_value == "Spacebar":  # Older browsers
            return Key.space

        logger.debug(f"Unmapped key: {key_value} (code: {event.get('code', 'N/A')})")
        return None

    def _release_all_keys(self):
        """Release all currently pressed keys."""
        # Note: This is a safety measure, but pynput doesn't track
        # pressed state, so we just clear our tracking set
        self._pressed_keys.clear()
        logger.debug("Released all tracked keys")

    def close(self):
        """Clean up resources."""
        self._release_all_keys()
        self._enabled = False
        logger.info("Input handler closed")

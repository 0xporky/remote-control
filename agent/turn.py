"""Time-limited TURN credentials (coturn REST API format).

Mirrors server/turn.py — the agent computes its own creds from the same
shared secret rather than making an HTTP call to the server.
"""

import base64
import hashlib
import hmac
import time


def make_credentials(secret: str, ttl_seconds: int, identifier: str = "agent") -> tuple[str, str]:
    expiry = int(time.time()) + ttl_seconds
    username = f"{expiry}:{identifier}"
    mac = hmac.new(secret.encode(), username.encode(), hashlib.sha1)
    credential = base64.b64encode(mac.digest()).decode()
    return username, credential

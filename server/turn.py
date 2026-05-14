"""Time-limited TURN credentials (coturn REST API format).

See https://datatracker.ietf.org/doc/html/draft-uberti-rtcweb-turn-rest-00.
Username is `<unix_expiry>:<identifier>`, credential is base64(HMAC-SHA1(secret, username)).
coturn validates this when started with `--use-auth-secret --static-auth-secret=<secret>`.
"""

import base64
import hashlib
import hmac
import time


def make_credentials(secret: str, ttl_seconds: int, identifier: str = "user") -> tuple[str, str, int]:
    """Returns (username, credential, expiry_unix_seconds)."""
    expiry = int(time.time()) + ttl_seconds
    username = f"{expiry}:{identifier}"
    mac = hmac.new(secret.encode(), username.encode(), hashlib.sha1)
    credential = base64.b64encode(mac.digest()).decode()
    return username, credential, expiry

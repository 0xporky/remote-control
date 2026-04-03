"""
Rate limiting for API endpoints.

Provides in-memory rate limiting to protect against brute force attacks.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_attempts: int = 5  # Maximum attempts allowed
    window_seconds: int = 60  # Time window in seconds
    lockout_seconds: int = 300  # Lockout duration after max attempts


class RateLimiter:
    """
    In-memory rate limiter for protecting endpoints.

    Tracks attempts per client IP and enforces rate limits.
    """

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        # Track attempts: ip -> list of timestamps
        self._attempts: Dict[str, list] = defaultdict(list)
        # Track lockouts: ip -> lockout_end_time
        self._lockouts: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> Tuple[bool, str]:
        """
        Check if a request from the client IP is allowed.

        Args:
            client_ip: The client's IP address

        Returns:
            Tuple of (is_allowed, message)
        """
        async with self._lock:
            current_time = time.time()

            # Check if currently locked out
            if client_ip in self._lockouts:
                lockout_end = self._lockouts[client_ip]
                if current_time < lockout_end:
                    remaining = int(lockout_end - current_time)
                    return False, f"Too many attempts. Try again in {remaining} seconds."
                else:
                    # Lockout expired, remove it
                    del self._lockouts[client_ip]
                    self._attempts[client_ip] = []

            # Clean old attempts outside the window
            window_start = current_time - self.config.window_seconds
            self._attempts[client_ip] = [
                t for t in self._attempts[client_ip] if t > window_start
            ]

            # Check if under the limit
            if len(self._attempts[client_ip]) >= self.config.max_attempts:
                # Apply lockout
                self._lockouts[client_ip] = current_time + self.config.lockout_seconds
                logger.warning(f"Rate limit exceeded for {client_ip}, locked out for {self.config.lockout_seconds}s")
                return False, f"Too many attempts. Try again in {self.config.lockout_seconds} seconds."

            return True, "OK"

    async def record_attempt(self, client_ip: str, success: bool = False):
        """
        Record an attempt from a client.

        Args:
            client_ip: The client's IP address
            success: If True, clears the attempt history (successful login)
        """
        async with self._lock:
            if success:
                # Clear attempts on successful login
                self._attempts.pop(client_ip, None)
                self._lockouts.pop(client_ip, None)
            else:
                # Record failed attempt
                self._attempts[client_ip].append(time.time())
                remaining = self.config.max_attempts - len(self._attempts[client_ip])
                if remaining > 0:
                    logger.info(f"Failed attempt from {client_ip}, {remaining} attempts remaining")

    async def cleanup(self):
        """Remove expired entries to prevent memory growth."""
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self.config.window_seconds

            # Clean old attempts
            expired_ips = []
            for ip, attempts in self._attempts.items():
                self._attempts[ip] = [t for t in attempts if t > window_start]
                if not self._attempts[ip]:
                    expired_ips.append(ip)

            for ip in expired_ips:
                del self._attempts[ip]

            # Clean expired lockouts
            expired_lockouts = [
                ip for ip, end_time in self._lockouts.items()
                if current_time >= end_time
            ]
            for ip in expired_lockouts:
                del self._lockouts[ip]

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "tracked_ips": len(self._attempts),
            "active_lockouts": len(self._lockouts),
        }


# Global rate limiter instance for login attempts
login_rate_limiter = RateLimiter(RateLimitConfig(
    max_attempts=5,
    window_seconds=60,
    lockout_seconds=300,
))

# Rate limiter for WebSocket connections
ws_rate_limiter = RateLimiter(RateLimitConfig(
    max_attempts=10,
    window_seconds=60,
    lockout_seconds=120,
))

"""
API Authentication — Token-based auth for the mobile companion API.
=====================================================================
Simple bearer-token authentication with auto-generated secrets.
Tokens are stored in a local file and can be regenerated from the dashboard.
"""

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from Jarvis.config import DATA_DIR

logger = logging.getLogger("jarvis.api.auth")

TOKEN_FILE = os.path.join(DATA_DIR, ".api_token")


@dataclass
class AuthToken:
    token: str
    created_at: float
    last_used: float = 0.0


def generate_token() -> str:
    """Generate a new cryptographically secure API token."""
    token = secrets.token_urlsafe(32)

    # Save to disk
    with open(TOKEN_FILE, "w") as f:
        f.write(token)

    logger.info("New API token generated")
    return token


def get_or_create_token() -> str:
    """Return the existing token or generate a new one."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
            if token:
                return token
    return generate_token()


def validate_token(provided: str) -> bool:
    """Validate a provided token against the stored token."""
    stored = get_or_create_token()
    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(provided, stored)


def get_token_hash() -> str:
    """Return a safe hash of the token (for display purposes)."""
    token = get_or_create_token()
    return hashlib.sha256(token.encode()).hexdigest()[:12]

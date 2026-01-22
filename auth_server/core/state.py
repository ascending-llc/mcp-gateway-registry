"""
Central in-memory state for OAuth flows.

This module exposes shared storage dictionaries used by the
device flow, authorization-code flow, and client registration.
Having a single authoritative module avoids accidental duplication
when routes are refactored or imported from tests.

In production these should be replaced by a persistent store
(Redis, database, etc.).
"""
import time
from typing import Dict, Any

# Device flow storage (in-memory, will migrate to Redis/MongoDB later)
device_codes_storage: Dict[str, Dict[str, Any]] = {}
user_codes_storage: Dict[str, str] = {}

# Client registration storage (in-memory)
registered_clients: Dict[str, Dict[str, Any]] = {}

# Authorization code storage for OAuth 2.0 Authorization Code Flow
authorization_codes_storage: Dict[str, Dict[str, Any]] = {}

# Refresh token storage (in-memory prototype). In production, persist in Redis/DB.
refresh_tokens_storage: Dict[str, Dict[str, Any]] = {}

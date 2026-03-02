"""Shared packages for MCP Gateway Registry."""

from registry_pkgs.core.jwt_utils import build_jwt_payload, decode_jwt, encode_jwt, get_token_kid
from registry_pkgs.core.scopes import load_scopes_config, map_groups_to_scopes

__version__ = "0.1.0"
__all__ = [
    "load_scopes_config",
    "map_groups_to_scopes",
    "build_jwt_payload",
    "encode_jwt",
    "decode_jwt",
    "get_token_kid",
]

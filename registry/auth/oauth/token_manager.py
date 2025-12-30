import asyncio
import time

from typing import Dict, Optional

from registry.models.models import OAuthTokens

from registry.utils.log import logger

class OAuthTokenManager:
    """OAuth token manager"""

    def __init__(self):
        self.tokens: Dict[str, Dict[str, OAuthTokens]] = {}  # user_id -> {server_name -> tokens}
        self._lock = asyncio.Lock()

    async def store_tokens(
            self,
            user_id: str,
            server_name: str,
            tokens: OAuthTokens
    ) -> None:
        """Store tokens"""
        async with self._lock:
            if user_id not in self.tokens:
                self.tokens[user_id] = {}

            self.tokens[user_id][server_name] = tokens
            logger.debug(f"Stored tokens for {user_id}/{server_name}")

    async def get_tokens(self, user_id: str, server_name: str) -> Optional[OAuthTokens]:
        """Get user's OAuth tokens"""
        async with self._lock:
            if user_id in self.tokens and server_name in self.tokens[user_id]:
                tokens = self.tokens[user_id][server_name]

                # Check if tokens are expired
                if self._are_tokens_expired(tokens):
                    logger.info(f"Tokens expired for {user_id}/{server_name}")
                    del self.tokens[user_id][server_name]
                    return None

                return tokens
            return None

    async def delete_tokens(self, user_id: str, server_name: str) -> bool:
        """Delete user's OAuth tokens"""
        async with self._lock:
            if user_id in self.tokens and server_name in self.tokens[user_id]:
                del self.tokens[user_id][server_name]
                logger.info(f"Deleted tokens for {user_id}/{server_name}")
                return True
            return False

    async def get_all_user_tokens(self, user_id: str) -> Dict[str, OAuthTokens]:
        """Get all tokens for user"""
        async with self._lock:
            if user_id in self.tokens:
                # Filter out expired tokens
                valid_tokens = {}
                for server_name, tokens in self.tokens[user_id].items():
                    if not self._are_tokens_expired(tokens):
                        valid_tokens[server_name] = tokens
                    else:
                        logger.debug(f"Filtered expired tokens for {user_id}/{server_name}")

                # Update storage, remove expired tokens
                self.tokens[user_id] = valid_tokens
                return valid_tokens
            return {}

    async def refresh_tokens(
            self,
            user_id: str,
            server_name: str,
            new_tokens: OAuthTokens
    ) -> bool:
        """Refresh tokens"""
        async with self._lock:
            if user_id not in self.tokens:
                self.tokens[user_id] = {}

            self.tokens[user_id][server_name] = new_tokens
            logger.info(f"Refreshed tokens for {user_id}/{server_name}")
            return True

    def _are_tokens_expired(self, tokens: OAuthTokens) -> bool:
        """Check if tokens are expired"""
        if not tokens.expires_at:
            return False

        # Add 5-second buffer to avoid edge cases
        buffer_time = 5
        return tokens.expires_at < (time.time() - buffer_time)

    async def cleanup_expired_tokens(self) -> int:
        """Cleanup all expired tokens, returns count cleaned"""
        async with self._lock:
            cleaned_count = 0
            users_to_remove = []

            for user_id, server_tokens in self.tokens.items():
                servers_to_remove = []

                for server_name, tokens in server_tokens.items():
                    if self._are_tokens_expired(tokens):
                        servers_to_remove.append(server_name)
                        cleaned_count += 1

                # Delete expired server tokens
                for server_name in servers_to_remove:
                    del server_tokens[server_name]

                # If user has no tokens, mark for removal
                if not server_tokens:
                    users_to_remove.append(user_id)

            # Delete users with no tokens
            for user_id in users_to_remove:
                del self.tokens[user_id]

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired tokens")

            return cleaned_count

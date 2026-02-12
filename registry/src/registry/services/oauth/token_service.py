import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from beanie import PydanticObjectId

from registry.models.emus import TokenType
from registry.models.oauth_models import OAuthTokens
from registry.services.user_service import user_service
from registry_db.models import IUser
from registry_db.models._generated.token import Token

logger = logging.getLogger(__name__)


class TokenService:
    async def get_user(self, user_id: str) -> IUser | None:
        user = await user_service.get_user_by_user_id(user_id)
        if not user:
            raise Exception(f"OAuth operation failed: User {user_id} not found")
        return user

    async def get_user_by_user_id(self, user_id: str) -> str:
        user = await self.get_user(user_id)
        return str(user.id)

    def _get_client_identifier(self, service_name: str) -> str:
        """Build client token identifier"""
        return f"mcp:{service_name}:client"

    def _get_refresh_identifier(self, service_name: str) -> str:
        """Build refresh token identifier"""
        return f"mcp:{service_name}:refresh"

    async def store_oauth_client_token(
        self, user_id: str, service_name: str, tokens: OAuthTokens, metadata: dict[str, Any] | None = None
    ) -> Token:
        """
        Store OAuth client token (access token)

        Args:
            user_id: User ID
            service_name: Service name (e.g., notion, agentcore, etc.)
            tokens: OAuth tokens object
            metadata: Additional metadata (e.g., OAuth configuration)

        Returns:
            Created or updated Token document
        """
        identifier = self._get_client_identifier(service_name)
        user = await self.get_user(user_id)
        user_obj_id = str(user.id)

        # Calculate expiration time
        expires_at = self._calculate_expiration(tokens.expires_in)

        # Check if token exists
        existing_token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_CLIENT.value,
                "identifier": identifier,
            }
        )

        if existing_token:
            # Update existing token
            existing_token.token = tokens.access_token
            existing_token.expiresAt = expires_at
            if metadata:
                existing_token.metadata = metadata
            existing_token.email = user.email
            await existing_token.save()
            logger.info(f"Updated OAuth client token for user={user_id}, service={service_name}")
            return existing_token
        else:
            # Create new token
            token_doc = Token(
                userId=PydanticObjectId(user_obj_id),
                type=TokenType.MCP_OAUTH_CLIENT.value,
                identifier=identifier,
                token=tokens.access_token,
                expiresAt=expires_at,
                metadata=metadata or {},
                email=user.email,
            )
            await token_doc.insert()
            logger.info(f"Created OAuth client token for user={user_id}, service={service_name}")
            return token_doc

    async def store_oauth_refresh_token(
        self, user_id: str, service_name: str, tokens: OAuthTokens, metadata: dict[str, Any] | None = None
    ) -> Token | None:
        """
        Store OAuth refresh token

        Args:
            user_id: User ID
            service_name: Service name
            tokens: OAuth tokens object
            metadata: Additional metadata
        """
        if not tokens.refresh_token:
            logger.debug(f"No refresh token provided for user={user_id}, service={service_name}")
            return None

        identifier = self._get_refresh_identifier(service_name)
        user = await self.get_user(user_id)
        user_obj_id = str(user.id)

        # Refresh tokens typically have a longer expiration time, set to 1 year here
        # Or set according to OAuth provider configuration
        expires_at = datetime.now(UTC) + timedelta(days=365)

        # Check if token exists
        existing_token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_REFRESH.value,
                "identifier": identifier,
            }
        )

        if existing_token:
            # Update existing token
            existing_token.token = tokens.refresh_token
            existing_token.expiresAt = expires_at
            if metadata:
                existing_token.metadata = metadata
            existing_token.email = user.email
            await existing_token.save()
            logger.info(f"Updated OAuth refresh token for user={user_id}, service={service_name}")
            return existing_token
        else:
            # Create new token
            token_doc = Token(
                userId=PydanticObjectId(user_obj_id),
                type=TokenType.MCP_OAUTH_REFRESH.value,
                identifier=identifier,
                token=tokens.refresh_token,
                expiresAt=expires_at,
                metadata=metadata or {},
            )
            token_doc.email = user.email
            await token_doc.insert()
            logger.info(f"Created OAuth refresh token for user={user_id}, service={service_name}")
            return token_doc

    async def store_oauth_tokens(
        self, user_id: str, service_name: str, tokens: OAuthTokens, metadata: dict[str, Any] | None = None
    ) -> dict[str, Token | None]:
        """
        Store complete OAuth tokens (access + refresh)

        This is the main storage method, which stores both access token and refresh token

        Args:
            user_id: User ID
            service_name: Service name
            tokens: OAuth tokens object
            metadata: Additional metadata (e.g., OAuth configuration)

        Returns:
            Dictionary containing client and refresh tokens
        """
        try:
            # Store access token
            client_token = await self.store_oauth_client_token(
                user_id=user_id, service_name=service_name, tokens=tokens, metadata=metadata
            )

            # Store refresh token (if exists)
            refresh_token = await self.store_oauth_refresh_token(
                user_id=user_id, service_name=service_name, tokens=tokens, metadata=metadata
            )

            return {"client": client_token, "refresh": refresh_token}

        except Exception as e:
            logger.error(f"Failed to store OAuth tokens: {e}", exc_info=True)
            raise

    async def get_oauth_client_token(self, user_id: str, service_name: str) -> Token | None:
        """
        Get OAuth client token

        Args:
            user_id: User ID
            service_name: Service name

        Returns:
            Token document or None
        """
        identifier = self._get_client_identifier(service_name)
        user_obj_id = await self.get_user_by_user_id(user_id)

        token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_CLIENT.value,
                "identifier": identifier,
            }
        )
        logger.debug(f"OAuth client token for user={user_id}, service={service_name}")

        # Check if token is expired
        if token and self._is_token_expired(token):
            logger.info(f"Token expired for user={user_id}, service={service_name}")
            return None

        return token

    async def get_oauth_refresh_token(self, user_id: str, service_name: str) -> Token | None:
        """
        Get OAuth refresh token

        Args:
            user_id: User ID
            service_name: Service name

        Returns:
            Token document or None
        """
        identifier = self._get_refresh_identifier(service_name)
        user_obj_id = await self.get_user_by_user_id(user_id)

        token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_REFRESH.value,
                "identifier": identifier,
            }
        )

        # Check if token is expired
        if token and self._is_token_expired(token):
            logger.info(f"Refresh token expired for user={user_id}, service={service_name}")
            return None

        return token

    async def get_oauth_tokens(self, user_id: str, service_name: str) -> OAuthTokens | None:
        """
        Get complete OAuth tokens and convert to OAuthTokens object

        Args:
            user_id: User ID
            service_name: Service name

        Returns:
            OAuthTokens object or None
        """
        client_token = await self.get_oauth_client_token(user_id, service_name)

        if not client_token:
            return None

        refresh_token = await self.get_oauth_refresh_token(user_id, service_name)

        # Convert to OAuthTokens object
        return OAuthTokens(  # nosec B106 - "Bearer" is token type, not token value
            access_token=client_token.token,
            refresh_token=refresh_token.token if refresh_token else None,
            token_type="Bearer",
            expires_in=self._calculate_expires_in(client_token.expiresAt),
            expires_at=int(client_token.expiresAt.timestamp()) if client_token.expiresAt else None,
        )

    async def delete_oauth_tokens(self, user_id: str, service_name: str) -> bool:
        """
        Delete user's OAuth tokens

        Args:
            user_id: User ID
            service_name: Service name

        Returns:
            Whether deletion was successful
        """
        user_obj_id = await self.get_user_by_user_id(user_id)

        # Delete client token
        client_identifier = self._get_client_identifier(service_name)
        client_result = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_CLIENT.value,
                "identifier": client_identifier,
            }
        )

        # Delete refresh token
        refresh_identifier = self._get_refresh_identifier(service_name)
        refresh_result = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_REFRESH.value,
                "identifier": refresh_identifier,
            }
        )

        deleted_count = 0
        if client_result:
            await client_result.delete()
            deleted_count += 1

        if refresh_result:
            await refresh_result.delete()
            deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} tokens for user={user_id}, service={service_name}")
            return True

        return False

    async def get_user_tokens(self, user_id: str, token_type: TokenType | None = None) -> list[Token]:
        """
        Get all user tokens

        Args:
            user_id: User ID
            token_type: Optional token type filter (TokenType.MCP_OAUTH_CLIENT or TokenType.MCP_OAUTH_REFRESH)

        Returns:
            List of Token documents
        """
        user_obj_id = await self.get_user_by_user_id(user_id)

        query = {"userId": user_obj_id}
        if token_type:
            query["type"] = token_type.value

        tokens = await Token.find(query).to_list()

        # Filter out expired tokens
        valid_tokens = [token for token in tokens if not self._is_token_expired(token)]

        return valid_tokens

    async def cleanup_expired_tokens(self) -> int:
        """
        Clean up all expired tokens

        Returns:
            Number of tokens cleaned up
        """
        now = datetime.now(UTC)

        # Find all expired tokens
        expired_tokens = await Token.find({"expiresAt": {"$lt": now}}).to_list()

        count = len(expired_tokens)

        # Delete expired tokens
        for token in expired_tokens:
            await token.delete()

        if count > 0:
            logger.info(f"Cleaned up {count} expired tokens")

        return count

    async def is_access_token_expired(self, user_id: str, service_name: str) -> bool:
        """
        Check if access token is expired or missing

        Returns:
            True if expired/missing, False if valid
        """
        client_token = await self.get_oauth_client_token(user_id, service_name)

        if not client_token:
            return True

        return self._is_token_expired(client_token)

    async def has_refresh_token(self, user_id: str, service_name: str) -> bool:
        """
        Check if user has a valid refresh token

        Returns:
            True if refresh token exists and not expired
        """
        refresh_token = await self.get_oauth_refresh_token(user_id, service_name)

        if not refresh_token:
            return False

        return not self._is_token_expired(refresh_token)

    async def get_access_token_status(self, user_id: str, service_name: str) -> tuple[Token | None, bool]:
        """
        Get access token and its validity status

        Returns:
            tuple: (token_doc, is_valid)
                - token_doc: Token document or None if not exists
                - is_valid: True if token exists and not expired, False otherwise
        """
        identifier = self._get_client_identifier(service_name)
        user_obj_id = await self.get_user_by_user_id(user_id)

        token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_CLIENT.value,
                "identifier": identifier,
            }
        )

        if not token:
            return None, False

        is_valid = not self._is_token_expired(token)
        return token, is_valid

    async def get_refresh_token_status(self, user_id: str, service_name: str) -> tuple[Token | None, bool]:
        """
        Get refresh token and its validity status

        Returns:
            tuple: (token_doc, is_valid)
                - token_doc: Token document or None if not exists
                - is_valid: True if token exists and not expired, False otherwise
        """
        identifier = self._get_refresh_identifier(service_name)
        user_obj_id = await self.get_user_by_user_id(user_id)

        token = await Token.find_one(
            {
                "userId": PydanticObjectId(user_obj_id),
                "type": TokenType.MCP_OAUTH_REFRESH.value,
                "identifier": identifier,
            }
        )

        if not token:
            return None, False

        is_valid = not self._is_token_expired(token)
        return token, is_valid

    def _calculate_expiration(self, expires_in: int | None) -> datetime:
        """
        Calculate token expiration time

        Args:
            expires_in: Expiration time (in seconds)

        Returns:
            datetime object of expiration time
        """
        if not expires_in:
            # Default to 1 hour
            expires_in = 3600

        return datetime.now(UTC) + timedelta(seconds=expires_in)

    def _calculate_expires_in(self, expires_at: datetime) -> int:
        """
        Calculate remaining valid time

        Args:
            expires_at: Expiration time

        Returns:
            Remaining seconds
        """
        now = datetime.now(UTC)

        # Ensure expires_at is timezone-aware
        if expires_at.tzinfo is None:
            # If timezone-naive, assume UTC
            expires_at = expires_at.replace(tzinfo=UTC)

        delta = expires_at - now
        return max(0, int(delta.total_seconds()))

    def _is_token_expired(self, token: Token) -> bool:
        """
        Check if token is expired

        Args:
            token: Token document

        Returns:
            Whether expired
        """
        if not token.expiresAt:
            return False
        now = datetime.now(UTC)

        # If expiresAt is timezone-naive, assume it's UTC and add timezone info
        if token.expiresAt.tzinfo is None:
            expires_at = token.expiresAt.replace(tzinfo=UTC)
        else:
            expires_at = token.expiresAt

        return expires_at <= (now + timedelta(seconds=3))


token_service = TokenService()

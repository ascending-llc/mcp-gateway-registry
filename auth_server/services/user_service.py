"""
User service for auth server - handles user lookups from MongoDB.
"""

import logging
from datetime import UTC, datetime

from packages.models import IUser

logger = logging.getLogger(__name__)


class UserService:
    """Service for user-related operations in auth server."""

    async def resolve_user_id(self, user_info: dict) -> str | None:
        """
        Resolve user_id from MongoDB by looking up user by username first, then email. If not found, create new user.

        Args:
            user_info: Dictionary containing user information with 'username' and/or 'email' fields

        Returns:
            user_id as string, None on exception
        """
        try:
            username = user_info.get("username")
            email = user_info.get("email")

            if not username and not email:
                logger.warning("No username or email found in user_info")
                return None

            # Try username first
            if username:
                user = await IUser.find_one({"username": username})
                if user:
                    logger.debug(f"✓ Resolved user_id from MongoDB by username: {user.id} for username: {username}")
                    return str(user.id)
                logger.debug(f"User not found by username: {username}, trying email...")

            # Then try email
            if email:
                user = await IUser.find_one({"email": email})
                if user:
                    logger.debug(f"✓ Resolved user_id from MongoDB by email: {user.id} for email: {email}")
                    return str(user.id)

            # If not found create new user
            logger.warning(
                f"User not found in MongoDB for username: {username}, email: {email}. Creating new user record."
            )
            existing_user = await IUser.find_one()
            new_user = IUser(
                name=user_info.get("name"),
                username=username,
                email=email or username,
                emailVerified=False,
                role="USER" if existing_user else "ADMIN",
                provider="openid",
                openidId=user_info.get("idp_id"),
                idOnTheSource=user_info.get("idp_id"),
                plugins=[],
                termsAccepted=False,
                backupCodes=[],
                refreshToken=[],
                favorites=[],
                createdAt=datetime.now(UTC),
                updatedAt=datetime.now(UTC),
            )

            created_user = await new_user.create()
            logger.info(
                f"Created new user record in MongoDB with id: {created_user.id} for username: {username}, email: {email}"
            )
            return str(created_user.id)
        except Exception as e:
            logger.error(f"Error resolving user_id from MongoDB: {type(e).__name__}: {e}")
            return None


# Global service instance
user_service = UserService()

"""
User service for user lookups by source ID or email.
"""
from typing import Optional
from packages.models._generated import IUser
import logging

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self):
        """Initialize sser service """
        logger.info("User service initialized")

    async def find_by_source_id(self, source_id: str) -> Optional[IUser]:
        """Find a user by idOnTheSource (Entra ID or similar)."""
        if not source_id:
            logger.warning("No source_id provided to find_by_source_id.")
            return None
        try:
            user = await IUser.find_one({"idOnTheSource": source_id})
            return user
        except Exception as e:
            logger.error(f"Error finding user by source_id '{source_id}': {e}")
            return None

    async def find_by_email(self, email: str) -> Optional[IUser]:
        """Find a user by email address."""
        if not email:
            logger.warning("No email provided to find_by_email.")
            return None
        try:
            user = await IUser.find_one({"email": email})
            return user
        except Exception as e:
            logger.error(f"Error finding user by email '{email}': {e}")
            return None

user_service = UserService()

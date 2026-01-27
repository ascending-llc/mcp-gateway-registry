from datetime import timezone, datetime
from typing import Optional
from beanie import PydanticObjectId
from packages.models import IUser
from registry.utils.log import logger


class UserService:

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

    async def get_user_by_user_id(self, user_id: str) -> Optional[IUser]:
        """
        Find a user by user_id
        """
        try:
            try:
                obj_id = PydanticObjectId(user_id)
            except Exception as e:
                logger.warning(f"Invalid user ID format: {user_id}")
                return None
            user = await IUser.get(obj_id)
            return user
        except Exception as e:
            logger.error(f"Error finding user by user_id '{user_id}': {e}")
            return None

    async def get_or_create_user(self, email: str) -> Optional[IUser]:
        """
        Get or create an user
            :param email: email of the user
        """
        user = await IUser.find_one({"email": email})
        if not user:
            now = datetime.now(timezone.utc)
            # Create user
            user_data = {
                "email": email,
                "emailVerified": False,
                "role": "USER",
                "provider": "local",
                "createdAt": now,
                "updatedAt": now
            }
            collection = IUser.get_pymongo_collection()
            await collection.insert_one(user_data)
            logger.info(f"Created user record for token storage: {email}")
            user = await IUser.find_one({"email": email})
        return user


user_service = UserService()

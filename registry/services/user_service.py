from datetime import timezone, datetime
from typing import Optional

from beanie import PydanticObjectId

from packages.models import IUser
from registry.utils.log import logger


class UserService:
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

    async def get_user_object_id(self, user_id: str) -> PydanticObjectId:
        """
        Get or create user's ObjectId

        Args:
            user_id: User ID (username)

        Returns:
            User's PydanticObjectId
        """
        user = await IUser.find_one({"username": user_id}) # TODO: the fix is at fix/auth_server branch

        if not user:
            now = datetime.now(timezone.utc)   # TODO: not need crate user
            email = f"{user_id}@local.mcp-gateway.internal"

            existing_user = await IUser.find_one({"email": email})
            if existing_user:
                return existing_user.id

            # Create user
            user_data = {
                "username": user_id,
                "email": email,
                "emailVerified": False,
                "role": "USER",
                "provider": "local",
                "createdAt": now,
                "updatedAt": now
            }

            collection = IUser.get_pymongo_collection()
            result = await collection.insert_one(user_data)
            logger.info(f"Created user record for token storage: {user_id}")
            return result.inserted_id

        return user.id


user_service = UserService()

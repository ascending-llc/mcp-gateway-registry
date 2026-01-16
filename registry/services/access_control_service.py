from datetime import datetime, timezone
from typing import Optional, List, Any
from packages.models._generated.aclEntry import IAclEntry
from packages.models._generated.accessRole import IAccessRole
from beanie import PydanticObjectId
import logging

logger = logging.getLogger(__name__)

class ACLService:
	async def grant_permission(
		self,
		principal_type: str,
		principal_id: Optional[Any],
		resource_type: str,
		resource_id: PydanticObjectId,
		granted_by: PydanticObjectId,
		role_id: Optional[PydanticObjectId] = None,
		perm_bits: Optional[int] = None,
	) -> IAclEntry:
		if principal_type in ["user", "group"] and not principal_id:
			raise ValueError("principal_id must be set for user/group principal_type")

		if not role_id and not perm_bits:
			raise ValueError("Permission bits must be set via perm_bits or role_id")
		
		if role_id:
			access_role = await IAccessRole.find_one({"_id": role_id})
			if not access_role:
				raise ValueError("Role not found")
			perm_bits = access_role.permBits

		# Check if an ACL entry already exists for this principal/resource
		try: 
			acl_entry = await IAclEntry.find_one({
				"principalType": principal_type,
				"principalId": principal_id,
				"resourceType": resource_type,
				"resourceId": resource_id
			})
			now = datetime.now(timezone.utc)
			if acl_entry:
				acl_entry.permBits = perm_bits
				acl_entry.roleId = role_id
				acl_entry.grantedBy = granted_by
				acl_entry.grantedAt = now
				acl_entry.updatedAt = now
				await acl_entry.save()
				return acl_entry
			else:
				# convert principal_id to str
				principal_id_str = str(principal_id)

				new_entry = IAclEntry(
					principalType=principal_type,
					principalId=principal_id_str,
					resourceType=resource_type,
					resourceId=resource_id,
					permBits=perm_bits,
					roleId=role_id,
					grantedBy=principal_id,
					grantedAt=now,
					createdAt=now,
					updatedAt=now
				)
				await new_entry.insert()
				return new_entry
		except Exception as e: 
			logger.error(f"Error finding/inserting ACL entry: {e}")
			raise ValueError(f"Error granting ACL permissions: {e}")
	
	async def check_permission(
		self,
		principal_type: str,
		principal_id: Any,
		resource_type: str,
		resource_id: PydanticObjectId,
		required_permission: float
	) -> bool:
		acl_entry = await IAclEntry.find_one({
			"principalType": principal_type,
			"principalId": principal_id,
			"resourceType": resource_type,
			"resourceId": resource_id
		})
		if acl_entry and acl_entry.permBits is not None:
			return (acl_entry.permBits & required_permission) == required_permission
		return False

	async def list_accessible_resources(
		self,
		principal_type: str,
		principal_id: str,
		resource_type: str,
		required_permissions: Optional[int] = 1
	) -> List[PydanticObjectId]:
		acl_entries = await IAclEntry.find({
			"principalType": {"$in": [principal_type, "public"]}, # check for public and user servers
			"principalId": str(principal_id),
			"resourceType": resource_type,
			"permBits": {"$gte": required_permissions}
		}).to_list()
		logger.info(f"Found {len(acl_entries)} accessible resources")
		return acl_entries

	async def remove_all_permissions(
		self,
		resource_type: str,
		resource_id: PydanticObjectId
	) -> int:
		try: 
			result = await IAclEntry.find({
				"resourceType": resource_type,
				"resourceId": resource_id
			}).delete()
			return result.deleted_count
		except Exception as e: 
			logger.error(f"Error deleting ACL entries for resource {resource_type} with ID {resource_id}: {e}")
			return 0

# Singleton instance
acl_service = ACLService()

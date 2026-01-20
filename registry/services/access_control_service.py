from datetime import datetime, timezone
from typing import Optional, List, Any
from packages.models._generated.aclEntry import IAclEntry
from packages.models._generated.accessRole import IAccessRole
from beanie import PydanticObjectId
from registry.services.constants import ResourceType, PermissionBits
import logging

logger = logging.getLogger(__name__)

class ACLService:
	async def grant_permission(
		self,
		principal_type: str,
		principal_id: Optional[Any],
		resource_type: str,
		resource_id: PydanticObjectId,
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
				acl_entry.grantedAt = now
				acl_entry.updatedAt = now
				await acl_entry.save()
				return acl_entry
			else:
				new_entry = IAclEntry(
					principalType=principal_type,
					principalId=principal_id,
					resourceType=resource_type,
					resourceId=resource_id,
					permBits=perm_bits,
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
			"principalId": {"userId": principal_id},
			"resourceType": resource_type,
			"resourceId": resource_id
		})
		if acl_entry and acl_entry.permBits is not None:
			return (acl_entry.permBits & required_permission) == required_permission
		return False

	# Not used currently
	async def list_accessible_resources(
		self,
		principal_type: str,
		principal_id: str,
		resource_type: str,
		required_permissions: Optional[int] = 1
	) -> List[PydanticObjectId]:
		acl_entries = await IAclEntry.find({
			"principalType": {"$in": [principal_type]}, # TODO: Check for public servers (principal_type "public")
			"principalId": {"userId": principal_id},
			"resourceType": resource_type,
			"permBits": {"$gte": required_permissions}
		}).to_list()
		logger.info(f"Found {len(acl_entries)} accessible resources")
		return acl_entries

	async def remove_permissions_for_resource(
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

	async def get_permissions_map_for_user_id(
		self,
		principal_type: str,
		principal_id: PydanticObjectId,
	) -> dict:
		"""
		Returns a dict mapping resource types to resourceIds, each with a dict of role names (VIEWER, EDITOR, MANAGER, OWNER) set to True/False based on permBits.
		Output keys match ResourceType enum values.
		Example:
		{
			"mcpServer": {
				"resourceId1": {"VIEW": true, "EDIT": true, "DELETE": true, "SHARE": false},
				"resourceId2": {"VIEW": true, "EDIT": false, ""DELETE": false, "SHARE": false}
			},
			"agent": {
				"resourceId3": {"VIEW": true, "EDIT": true, "DELETE": true, "SHARE": true}
			}
		}
		"""

		try: 
			acl_entries = await IAclEntry.find({
				"principalType": principal_type,
				"principalId": {"userId": principal_id},
				"resourceType": {"$in": [rt.value for rt in ResourceType]}
			}).to_list()

			result = {}
			for entry in acl_entries:
				rtype = entry.resourceType
				rid = str(entry.resourceId)
				if rtype not in result:
					result[rtype] = {}
				result[rtype][rid] = {
					"VIEW": entry.permBits >= PermissionBits.VIEW,
					"EDIT": entry.permBits >= PermissionBits.EDIT,
					"DELETE": entry.permBits >= PermissionBits.DELETE,
					"SHARE": entry.permBits >= PermissionBits.SHARE,
				}
			logger.info(f"ACL permissions map for user id {principal_id}: {result}")
			return result
		except Exception as e: 
			logger.error(f"Error fetching ACL permissions map for user id: {principal_id}: {e}")
			return {}
	
# Singleton instance
acl_service = ACLService()

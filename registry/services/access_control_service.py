from datetime import datetime, timezone
from typing import Optional, List, Any
from packages.models._generated import (
	IAclEntry,
	IAccessRole,
)
from beanie import PydanticObjectId
from registry.services.constants import ResourceType, PermissionBits, PrincipalType
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
		"""
		Grant ACL permission to a principal (user or group) for a specific resource.

		Args:
			principal_type (str): Type of principal ('user', 'group', etc.).
			principal_id (Any): ID of the principal (user ID, group ID, etc.).
			resource_type (str): Type of resource (see ResourceType enum).
			resource_id (PydanticObjectId): Resource document ID.
			role_id (Optional[PydanticObjectId]): Optional role ID to derive permission bits.
			perm_bits (Optional[int]): Permission bits to assign (overrides role if provided).

		Returns:
			IAclEntry: The upserted or newly created ACL entry.

		Raises:
			ValueError: If required parameters are missing or invalid, or if upsert fails.
		"""
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
			logger.error(f"Error upserting ACL entry: {e}")
			raise ValueError(f"Error upserting ACL permissions: {e}")
	
	# Not used
	async def check_permission(
		self,
		principal_type: str,
		principal_id: str,
		resource_type: str,
		resource_id: PydanticObjectId,
		required_permission: float
	) -> bool:
		"""
		Check if a principal has the required permission for a resource.

		Args:
			principal_type (str): Type of principal ('user', 'group', etc.).
			principal_id (str): ID of the principal (user ID, group ID, etc.).
			resource_type (str): Type of resource (see ResourceType enum).
			resource_id (PydanticObjectId): Resource document ID.
			required_permission (float): Permission bit(s) required.

		Returns:
			bool: True if the principal has the required permission, False otherwise.

		Raises:
			None (returns False if not found or insufficient permissions).
		"""
		acl_entry = await IAclEntry.find_one({
			"principalType": principal_type,
			"principalId": {"userId": principal_id},
			"resourceType": resource_type,
			"resourceId": resource_id
		})
		if acl_entry and acl_entry.permBits is not None:
			return (acl_entry.permBits & required_permission) == required_permission
		return False

	# Not used
	async def list_accessible_resources(
		self,
		principal_type: str,
		principal_id: str,
		resource_type: str,
		required_permissions: Optional[int] = 1
	) -> List[PydanticObjectId]:
		"""
		List all resource IDs of a given type that a principal can access with the required permissions.

		Args:
			principal_type (str): Type of principal ('user', 'group', etc.).
			principal_id (str): ID of the principal (user ID, group ID, etc.).
			resource_type (str): Type of resource (see ResourceType enum).
			required_permissions (Optional[int]): Minimum permission bits required (default: 1).

		Returns:
			List[PydanticObjectId]: List of resource IDs accessible by the principal.

		Raises:
			None (returns empty list on error).
		"""
		acl_entries = await IAclEntry.find({
			"principalType": {"$in": [principal_type, PrincipalType.PUBLIC.value]},
			"principalId": {"userId": principal_id},
			"resourceType": resource_type,
			"permBits": {"$gte": required_permissions}
		}).to_list()
		logger.info(f"Found {len(acl_entries)} accessible resources")
		return acl_entries

	async def delete_acl_entries_for_resource(
		self,
		resource_type: str,
		resource_id: PydanticObjectId,
		author_id: PydanticObjectId = None
	) -> int:
		"""
		Delete all ACL entries for a given resource, with optional preservation of the author's permissions.

		Args:
			resource_type (str): Type of resource (see ResourceType enum).
			resource_id (PydanticObjectId): Resource document ID.
			author_id (Optional[PydanticObjectId]): If provided, preserves ACL entry for the author.

		Returns:
			int: Number of ACL entries deleted.

		Raises:
			None (returns 0 on error).
		"""
		try: 
			# Remove all entries except the resource author 
			# used when making a resource public
			if author_id: 
				result = await IAclEntry.find({
					"resourceType": resource_type,
					"resourceId": resource_id,
					"$nor": [{"principalId.userId": author_id}]
				}).delete()
				return result.deleted_count
			else: 
				# Remove all entries including the author
				# used when deleting a resource
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
		principal_id: str,
	) -> dict:
		"""
		Return a permissions map for a user, showing access rights for each resource type and resource ID.

		Args:
			principal_type (str): Type of principal ('user', 'group', etc.).
			principal_id (str): ID of the principal (user ID, group ID, etc.).

		Returns:
			dict: Mapping of resource types to resource IDs, each with a dict of permission flags (VIEW, EDIT, DELETE, SHARE).

		Example:
		{
			"mcpServer": {
				"resourceId1": {"VIEW": True, "EDIT": True, "DELETE": True, "SHARE": False},
				"resourceId2": {"VIEW": True, "EDIT": False, "DELETE": False, "SHARE": False}
			},
			"agent": {
				"resourceId3": {"VIEW": True, "EDIT": True, "DELETE": True, "SHARE": True}
			}
		}

		Raises:
			None (returns empty dict on error).
		"""

		try:
			resource_types = [rt.value for rt in ResourceType]
			query = {
				"principalType": {"$in": [principal_type, PrincipalType.PUBLIC.value]},
				"resourceType": {"$in": resource_types},
				"$or": [
					{"principalId": {"userId": PydanticObjectId(principal_id)}},
					{"principalId": None}
				]
			}
			acl_entries = await IAclEntry.find(query).to_list()
			result = {rt.value: {} for rt in ResourceType}
			for entry in acl_entries:
				rtype = entry.resourceType
				rid = str(entry.resourceId)
				result[rtype][rid] = {
					"VIEW": entry.permBits >= PermissionBits.VIEW,
					"EDIT": entry.permBits >= PermissionBits.EDIT,
					"DELETE": entry.permBits >= PermissionBits.DELETE,
					"SHARE": entry.permBits >= PermissionBits.SHARE,
				}
			return result
		except Exception as e: 
			logger.error(f"Error fetching ACL permissions map for user id: {principal_id}: {e}")
			return {}
	

	async def delete_permission(
		self,
		resource_type: str,
		resource_id: PydanticObjectId,
		principal_type: str,
		principal_id: Any
	) -> int:
		"""
		Remove a single ACL entry for a given resource, principal type, and principal ID.

		Args:
			resource_type (str): Type of resource (see ResourceType enum).
			resource_id (PydanticObjectId): Resource document ID.
			principal_type (str): Type of principal ('user', 'group', etc.).
			principal_id (Any): ID of the principal (user ID, group ID, etc.).

		Returns:
			int: Number of deleted entries (0 or 1).

		Raises:
			None (returns 0 on error).
		"""
		try:
			query = {
				"resourceType": resource_type,
				"resourceId": resource_id,
				"principalType": principal_type,
				"principalId": {"userId": principal_id}
			}
			result = await IAclEntry.find(query).delete()
			if hasattr(result, "deleted_count"):
				return result.deleted_count
			return 0
		except Exception as e:
			logger.error(f"Error revoking ACL entry for resource {resource_type} with ID {resource_id}: {e}")
			return 0


# Singleton instance
acl_service = ACLService()

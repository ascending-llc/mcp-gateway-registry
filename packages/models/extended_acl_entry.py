"""
Extended ACL Entry Model for Registry-Specific Flexibility

This module extends the auto-generated IAclEntry with a more flexible principalId field.
The base model (_generated/aclEntry.py) should NOT be modified as it's auto-generated.
"""


from beanie import PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from packages.models._generated.aclEntry import IAclEntry


class ExtendedAclEntry(IAclEntry):
	"""
	Extended ACL Entry Document
	principalId is ObjectId, str, or None
	roleId, inheritedFrom,grantedBy are ObjectIds and cannot be subject to string pattern constraints
	"""
	principalId: PydanticObjectId | str | None = Field(default=None)
	roleId: PydanticObjectId | None = Field(default=None)  # references IAccessRole collection
	inheritedFrom: PydanticObjectId | None = Field(default=None)
	grantedBy: PydanticObjectId | None = Field(default=None)  # references IUser collection

	class Settings:
		name = "aclentries"
		keep_nulls = False
		use_state_management = True

		indexes = [
			[("principalId", 1)],
			[("resourceId", 1)],
			IndexModel([("inheritedFrom", 1)], sparse=True),
			[("principalId", 1), ("principalType", 1), ("resourceType", 1), ("resourceId", 1)],
			[("resourceId", 1), ("principalType", 1), ("principalId", 1)],
			[("principalId", 1), ("permBits", 1), ("resourceType", 1)],
		]


IAclEntry = ExtendedAclEntry

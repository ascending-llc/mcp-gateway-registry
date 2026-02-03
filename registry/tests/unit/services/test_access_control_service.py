from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from registry.core.acl_constants import PermissionBits, ResourceType
from registry.services.access_control_service import ACLService


class TestACLService:
    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_grant_permission_new_entry(self, mock_acl_entry):
        service = ACLService()
        mock_acl_entry.find_one = AsyncMock(return_value=None)

        # IAclEntry() returns an AsyncMock, whose insert is also an AsyncMock
        new_entry = AsyncMock()
        new_entry.insert = AsyncMock()
        mock_acl_entry.return_value = new_entry
        with patch("registry.services.access_control_service.IAclEntry", mock_acl_entry):
            entry = await service.grant_permission(
                principal_type="user",
                principal_id={"id": "user1"},
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(),
                perm_bits=PermissionBits.EDIT,
            )
            new_entry.insert.assert_awaited()

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_grant_permission_update_existing(self, mock_acl_entry):
        service = ACLService()
        existing_entry = MagicMock()
        existing_entry.save = AsyncMock()
        mock_acl_entry.find_one = AsyncMock(return_value=existing_entry)
        with patch("registry.services.access_control_service.datetime") as mock_datetime:
            mock_datetime.now.return_value = MagicMock()
            entry = await service.grant_permission(
                principal_type="user",
                principal_id={"id": "user1"},
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(),
                perm_bits=PermissionBits.EDIT,
            )
            existing_entry.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_grant_permission_missing_principal_id(self):
        service = ACLService()
        with pytest.raises(ValueError):
            await service.grant_permission(
                principal_type="user",
                principal_id=None,
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(),
                perm_bits=PermissionBits.EDIT,
            )

    @pytest.mark.asyncio
    async def test_grant_permission_missing_perm_bits_and_role(self):
        service = ACLService()
        with pytest.raises(ValueError):
            await service.grant_permission(
                principal_type="user",
                principal_id={"id": "user1"},
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(),
            )

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_delete_acl_entries_for_resource(self, mock_acl_entry):
        service = ACLService()
        mock_result = MagicMock()
        mock_result.deleted_count = 2
        mock_acl_entry.find.return_value.delete = AsyncMock(return_value=mock_result)
        deleted = await service.delete_acl_entries_for_resource(
            resource_type=ResourceType.MCPSERVER.value, resource_id=PydanticObjectId()
        )
        assert deleted == 2

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_delete_acl_entries_for_resource_exception(self, mock_acl_entry):
        service = ACLService()
        mock_acl_entry.find.return_value.delete = AsyncMock(side_effect=Exception("fail"))
        deleted = await service.delete_acl_entries_for_resource(
            resource_type=ResourceType.MCPSERVER.value, resource_id=PydanticObjectId()
        )
        assert deleted == 0

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_get_permissions_map_for_user_id(self, mock_acl_entry):
        service = ACLService()
        entry = MagicMock()
        entry.resourceType = ResourceType.MCPSERVER.value
        entry.resourceId = PydanticObjectId()
        entry.permBits = PermissionBits.EDIT
        mock_acl_entry.find.return_value.to_list = AsyncMock(return_value=[entry])
        result = await service.get_permissions_map_for_user_id("user", PydanticObjectId())
        assert ResourceType.MCPSERVER.value in result
        assert isinstance(result[ResourceType.MCPSERVER.value], dict)

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_delete_permission(self, mock_acl_entry):
        service = ACLService()
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_acl_entry.find.return_value.delete = AsyncMock(return_value=mock_result)
        deleted_count = await service.delete_permission(
            resource_type=ResourceType.MCPSERVER.value,
            resource_id=PydanticObjectId(),
            principal_type="user",
            principal_id=PydanticObjectId(),
        )
        assert deleted_count == 1

    @pytest.mark.asyncio
    @patch("registry.services.access_control_service.IAclEntry")
    async def test_delete_permission_exception(self, mock_acl_entry):
        service = ACLService()
        mock_acl_entry.find.return_value.delete = AsyncMock(side_effect=Exception("fail"))
        deleted = await service.delete_permission(
            resource_type=ResourceType.MCPSERVER.value,
            resource_id=PydanticObjectId(),
            principal_type="user",
            principal_id="user1",
        )
        assert deleted == 0

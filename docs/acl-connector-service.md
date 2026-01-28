# ACL Service design

## Table of Contents
1. [Introduction](#introduction)
    - [Problem Statement](#problem-statement)
    - [Objectives](#objectives)
2. [Existing Role-Based Permission System](#existing-role-based-permission-system)
    - [Terminology](#terminology)
    - [Existing ACL Service](#existing-acl-service)
    - [Compatibility and Gaps with Current Requirements](#compatibility-and-gaps-with-current-requirements)
    - [Solution: Bridging the Gaps](#solution-bridging-the-gaps)
3. [ACL Service Design](#acl-service-design)
    - [High-Level Authentication & Authorization Sequence Flow](#high-level-authentication--authorization-sequence-flow)
    - [Data Models](#data-models)
    - [Service Design](#service-design)
4. [Jarvis Integration](#jarvis-integration)
    - [Authentication Middleware / JWT Forwarding](#authentication-middleware)
5. [Additional Considerations](#additional-considerations)
    - [Server Registration Form Updates](#server-registration-form-updates)
    - [ACL Service Cache](#acl-service-cache)
6. [Roadmap](#roadmap)
7. [Etc Notes](#etc-notes)


## Introduction

### Problem Statement

The MCP Gateway Registry requires fine-grained Access Control List (ACL) capabilities to support secure environments for MCP servers and A2A agents. Currently, all end users have access to the same set of connectors, which does not meet customer requirements for object-level permissions. To address this, we will introduce an ACL service in the MCP registry project that enables:

- Object-level permissions for servers and agents 
- Control over visibility and access for individual users, user groups, and public (everyone)
- Integration with a MongoDB-backed persistence layer for scalable, transactional storage

This ACL service will be foundational for enforcing secure access and will be compatible with the shared data models and interfaces used in the Jarvis project.

### Objectives

- Design an ACL service that allows admins to share an MCP Server or Agent with:
  - Everyone (public)
  - Specific user groups
  - Specific users
- Ensure compatibility with existing data models and interfaces (as defined in jarvis-api and shared schemas)
- Leverage MongoDB as the single source of truth for ACL metadata and permissions
- Support role-based access control (RBAC) and object-level permissions for all resources

## Existing Role-Based Permission System

An ACLService is already implemented in the Jarvis project. Prior to defining the registry-specific approach, it is essential to review this existing design and assess its compatibility with the updated requirements for sharing connectors (MCP servers and agents) across user, group, and public scopes.

### Terminology
- **Principals**: Entities that can be granted permissions (individual users, groups, public)
- **Roles**: Predefined sets of permissions. Each role is associated with a resource type  and maps to permission bits (permBits) 
- **Resources**: Items that require access control (mcp servers, agents), identified by resourceType and resourceId.
- **Permissions**: Numeric bitmasks that define allowed actions (view, edit).

### Existing ACL Service
The existing [ACLService](https://github.com/ascending-llc/jarvis-api/blob/deploy/packages/api/src/acl/accessControlService.ts) in Jarvis exposes several methods for managing object-level permissions. In the list below, methods that are misaligned with current requirements are shown with strikethroughs, while the remaining methods are candidates for refactoring to meet the updated needs:

- `grantPermission`: Grants permissions to a principal for specific resources using a permission set optionally defined in a role
- `findAccessibleResources`: Finds all resources of a specific type that a user has access to with specific permission bits
- ~~`findPubliclyAccessibleResources`: Find all publicly accessible resources of a specific type~~
- `getResourcePermissionsMap`: Get effective permissions for multiple resources in a batch operation
- `removeAllPermissions`: Removes all permissions for a resource
- `checkPermission`: Checks if a specific user has permissions on a resource
- ~~`validateResourceType`: Validates a resource types and manages permission schemas.~~

**Compatibility with Requirements:**
1. Supports permissions for users, groups, and public.
2. Enables fine-grained control via permission bits and roles.

**Misalignment with Requirements:**
1. Some functions (e.g., `findAccessibleResources`) are user-only and omit groups; others (e.g., `grantPermission`) need refactoring for broader principal support.
2. No automated sync of enums/constants (roles, permission bits) between Jarvis and registry schemas.
3. No mechanism for passing authenticated user context from Jarvis to the registry, blocking accurate permission checks.

**Proposed Solutions**
1. Design the registry ACL service with a minimal, focused set of functions that directly satisfy the current requirements for sharing resources with users, groups, and public, while allowing for future extensibility as additional use cases emerge.

2. Implement automated synchronization of enums and constants (such as roles and permission bits) between Jarvis and the registry project to maintain schema consistency and prevent drift.

3. Use session cookie authentication (`mcp-gateway-session`) for browser/UI users.

## ACL Service Design

### High-Level Authentication & Authorization Sequence Flow

**Note:** Jarvis users authenticate to the registry using a session cookie named `mcp-gateway-session`. This cookie is set after successful login and is included in all subsequent requests to the registry for authentication and permission checks.

```mermaid
sequenceDiagram
    participant U as User Browser
    participant R as Registry Backend (FastAPI)
    participant A as Auth Server (OAuth2)
    participant DB as MongoDB

    U->>R: Request login page
    R->>A: Fetch available OAuth2 providers
    R-->>U: Render login page with providers
    U->>R: Select provider, request /redirect/{provider}
    R->>A: Redirect to Auth Server for OAuth2 login
    U->>A: Authenticate (OAuth2 flow)
    A->>U: Redirect with signed user info (JWT or payload)
    U->>R: Callback to /redirect with signed user info
    R->>DB: Lookup or create user in MongoDB
    DB-->>R: User record
    R->>U: Set session cookie `mcp-gateway-session`, redirect to dashboard
    U->>R: Subsequent API requests with `mcp-gateway-session` cookie
    R->>DB: (If needed) Load user/ACL data for permissions
    DB-->>R: User/ACL data
    R-->>U: Serve protected resources based on permissions
```

### ACL Implementation

#### Field Definitions

Required Fields: 
- `principalType`: String - The type of principal (user, group, or public)
- `principalId?`: Mixed - The ID of the principal (objectId for user/group, null for "public")
- `resourceType`: String - The type of resource (MCP Server, Agent)
- `resourceId`: ObjectId - The ID of the resource
- `permBits`: Number - The permission bits 

Optional Fields:
- `principalModel?`: String - The MongoDB model, null for "public". Can be used to support bulk updates 
- `roleId?:` ObjectId - The ID of the role whose permissions are being inherited 
- `inheritedFrom?`: ObjectId - ID of the resource this permission is inherited from
- `grantedBy?`: ObjectId - ID of the user who granted this permission
- `grantedAt?`: String (ISO 8601) -  When this permission was granted

#### MongoDB Schema Model
MongoDB `ACLEntry`

```bson
{
  _id: ObjectId("..."),
  principalType: "user" | "group" | "public",
  principalId: "..." | null,
  principalModel: "..." | null,
  resourceType: "mcpServer" | "agent"
  resourceId: ObjectId("..."),
  permBits: NumberLong(1),
  roleId: ObjectId("...") | null,
  inheritedFrom: ObjectId("...") | null,
  grantedBy: ObjectId("...") | null,
  grantedAt: ISODate("..."),
  createdAt: ISODate("...")
  updatedAt: ISODate("...")
}
```
**Supporting Enums / Constants**
The `ACLEntry` relies on the following enums/constants exported by `librechat-data-provider`:

- **principalType**
- **principalModel**
- **ResourceType**
- **PermBits**
- **AccessRoleIds**

These enums are not currently imported via `import-schema`. Updates to the `import-schema` tool or an additional import tool will be needed to keep the supporting models in-line with jarvis-api. 


### Service Design

The ACL service needs to facilitate the following operations: 
1. Admin/Owner can share resource with specific user 
2. Admin/Owner can share resource with specific group
3. Admin/Owner can share resource with everyone 
4. Admin/Owner can remove all permissions from resource (in the case of resource deletion)

```python
from datetime import datetime, timezone
from typing import Optional, Union
from packages.models._generated import IAccessRole
from packages.models.extended_acl_entry import ExtendedAclEntry as IAclEntry
from beanie import PydanticObjectId
from registry.core.acl_constants import ResourceType, PermissionBits, PrincipalType

class ACLService:
    async def grant_permission(
        self,
        principal_type: str,
        principal_id: Optional[Union[PydanticObjectId, str]],
        resource_type: str,
        resource_id: PydanticObjectId,
        role_id: Optional[PydanticObjectId] = None,
        perm_bits: Optional[int] = None,
    ) -> IAclEntry:
        """
        Grant ACL permission to a principal (user or group) for a specific resource.
        """

    async def delete_acl_entries_for_resource(
        self,
        resource_type: str,
        resource_id: PydanticObjectId,
        perm_bits_to_delete: Optional[int] = None
    ) -> int:
        """
        Bulk delete ACL entries for a given resource, optionally deleting all entries with permBits less than or equal to the specified value.
        """

    async def get_permissions_map_for_user_id(
        self,
        principal_type: str,
        principal_id: PydanticObjectId,
    ) -> dict:
        """
        Return a permissions map for a user, showing access rights for each resource type and resource ID.
        """

    async def delete_permission(
        self,
        resource_type: str,
        resource_id: PydanticObjectId,
        principal_type: str,
        principal_id: Optional[Union[PydanticObjectId, str]]
    ) -> int:
        """
        Remove a single ACL entry for a given resource, principal type, and principal ID.
        """
```


### Exposed API Endpoints

The following REST API endpoints are exposed for ACL management:

- **GET /permissions/servers/{server_id}**
    - **Purpose:** Get the current user's permissions for a specific server resource.
    - **Response:**
        ```json
        {
            "server_id": "<id>",
            "permissions": {"VIEW": true, "EDIT": false, ...}
        }
        ```

- **PUT /permissions/servers/{server_id}**
    - **Purpose:** Update ACL permissions for a specific server.
    - **Request:**
        ```json
        {
            "public": true,
            "removed": [ ... ],
            "updated": [ ... ]
        }
        ```
    - **Response:**
        ```json
        {
            "message": "Updated <count> and deleted <count> permissions",
            "results": {"server_id": "<id>"}
        }
        ```
 
This pattern can be extended to include APIs for agent, prompt groups, and other resource types.

## Additional Considerations

### ACL Service Cache
TBD after evaulating performance of initial service implementation

## Roadmap 
Listed below are work items that need to be completed for ACL Service Integration 
- Write the ACLService in the registry project
- Write authentication middleware to connect jarvis and registry
- Refactor `import-schema` tool to include constants and enums from `librechat/data-provider`
- Update the Resource-based services to incorporate ACL permissions
- point jarvis to `server_service_v1`

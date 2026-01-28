#########################################################
#  DUPLICATED JARVIS SCHEMA 					        # 
#  DELETE AFTER IMPORT TOOLING REFACTOR                 # 
#########################################################

from enum import Enum

# PermissionBits for bitwise operations
class PermissionBits:
	VIEW = 1      # 0001
	EDIT = 2      # 0010
	DELETE = 4    # 0100
	SHARE = 8     # 1000

# RoleBits enum using PermissionBits
class RoleBits:
	VIEWER = PermissionBits.VIEW                # 1
	EDITOR = PermissionBits.VIEW | PermissionBits.EDIT         # 3
	MANAGER = PermissionBits.VIEW | PermissionBits.EDIT | PermissionBits.DELETE  # 7
	OWNER = PermissionBits.VIEW | PermissionBits.EDIT | PermissionBits.DELETE | PermissionBits.SHARE  # 15

# Permissions enum (string values)
class Permissions(str, Enum):
	SHARED_GLOBAL = 'SHARED_GLOBAL'
	USE = 'USE'
	CREATE = 'CREATE'
	UPDATE = 'UPDATE'
	READ = 'READ'
	READ_AUTHOR = 'READ_AUTHOR'
	SHARE = 'SHARE'
	OPT_OUT = 'OPT_OUT'  # Can disable if desired
	VIEW_USERS = 'VIEW_USERS'
	VIEW_GROUPS = 'VIEW_GROUPS'
	VIEW_ROLES = 'VIEW_ROLES'

class PrincipalType(str, Enum):
	USER = "user"
	GROUP = "group"
	PUBLIC = "public"
	ROLE = "role"

class PrincipalModel(str, Enum):
	USER = "User"
	GROUP = "Group"
	ROLE = "Role"

class ResourceType(str, Enum):
	AGENT = "agent"
	PROMPTGROUP = "promptGroup"
	MCPSERVER = "mcpServer"

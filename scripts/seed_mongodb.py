#!/usr/bin/env python3
"""
MongoDB Seed Script for MCP Gateway Registry

Seeds sample data for users, keys, tokens, and MCP servers.
Includes examples of servers using API keys and OAuth tokens.

Usage:
    python scripts/seed_mongodb.py          # Seed data (default)
    python scripts/seed_mongodb.py seed     # Seed data
    python scripts/seed_mongodb.py clean    # Clean all collections
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.database.mongodb import MongoDB
from packages.models._generated.user import IUser
from packages.models._generated.key import Key
from packages.models._generated.token import Token
from packages.models._generated.mcpServer import MCPServerDocument
from registry.utils.crypto_utils import encrypt_auth_fields


async def seed_users():
    """Seed sample users."""
    print("Seeding users...")

    users_data = [
        {
            "name": "Admin User",
            "username": "admin",
            "email": "admin@example.com",
            "emailVerified": True,
            "password": "$2b$10$abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH",  # hashed password
            "role": "ADMIN",
            "provider": "local",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "name": "John Developer",
            "username": "johndoe",
            "email": "john.doe@example.com",
            "emailVerified": True,
            "password": "$2b$10$abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH",
            "role": "USER",
            "provider": "local",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "name": "Jane Smith",
            "username": "janesmith",
            "email": "jane.smith@example.com",
            "emailVerified": True,
            "password": "$2b$10$abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH",
            "role": "USER",
            "provider": "local",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "name": "Test User",
            "username": "testuser",
            "email": "test.user@example.com",
            "emailVerified": True,
            "password": "$2b$10$abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGH",
            "role": "USER",
            "provider": "local",
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
    ]

    created_users = []
    for user_data in users_data:
        # Check if user already exists
        existing_user = await IUser.find_one(IUser.email == user_data["email"])
        if existing_user:
            print(f"  User {user_data['email']} already exists, skipping...")
            created_users.append(existing_user)
        else:
            user = IUser(**user_data)
            await user.insert()
            created_users.append(user)
            print(f"  Created user: {user_data['email']}")

    return created_users


async def seed_keys(users):
    """Seed API keys for users."""
    print("Seeding API keys...")

    keys_data = [
        {
            "userId": users[0].id,  # Admin user
            "name": "Admin API Key",
            "value": "sk_admin_1234567890abcdefghijklmnopqrstuvwxyz",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=365),
        },
        {
            "userId": users[1].id,  # John Developer
            "name": "Development Key",
            "value": "sk_dev_abcdefghijklmnopqrstuvwxyz1234567890",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=90),
        },
        {
            "userId": users[1].id,  # John Developer
            "name": "Testing Key",
            "value": "sk_test_xyz789012345678901234567890abcdefgh",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=30),
        },
        {
            "userId": users[2].id,  # Jane Smith
            "name": "Production API Key",
            "value": "sk_prod_mnopqrstuvwxyz1234567890abcdefghijkl",
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=180),
        },
    ]

    created_keys = []
    for key_data in keys_data:
        # Check if key already exists
        existing_key = await Key.find_one(Key.value == key_data["value"])
        if existing_key:
            print(f"  Key {key_data['name']} already exists, skipping...")
            created_keys.append(existing_key)
        else:
            key = Key(**key_data)
            await key.insert()
            created_keys.append(key)
            print(f"  Created key: {key_data['name']}")

    return created_keys


async def seed_tokens(users):
    """Seed OAuth tokens for users."""
    print("Seeding tokens...")

    tokens_data = [
        {
            "userId": users[2].id,  # Jane Smith (GitHub user)
            "email": users[2].email,
            "type": "oauth",
            "identifier": "mcp:github:client",
            "token": "gho_abcdefghijklmnopqrstuvwxyz1234567890",
            "createdAt": datetime.now(timezone.utc),
            "expiresAt": datetime.now(timezone.utc) + timedelta(hours=24),
            "metadata": {
                "provider": "github",
                "scope": "read:user,repo",
                "token_type": "bearer",
            },
        },
        {
            "userId": users[3].id,  # OAuth User (Google)
            "email": users[3].email,
            "type": "oauth",
            "identifier": "mcp:google:client",
            "token": "ya29.a0abcdefghijklmnopqrstuvwxyz123456789",
            "createdAt": datetime.now(timezone.utc),
            "expiresAt": datetime.now(timezone.utc) + timedelta(hours=1),
            "metadata": {
                "provider": "google",
                "scope": "openid email profile",
                "token_type": "bearer",
                "refresh_token": "1//abcdefghijklmnopqrstuvwxyz",
            },
        },
        {
            "userId": users[1].id,  # John Developer
            "email": users[1].email,
            "type": "refresh",
            "identifier": "mcp:local:refresh",
            "token": "rt_dev_xyz123456789abcdefghijklmnopqrstuv",
            "createdAt": datetime.now(timezone.utc),
            "expiresAt": datetime.now(timezone.utc) + timedelta(days=30),
            "metadata": {
                "ip": "192.168.1.100",
                "user_agent": "Mozilla/5.0",
            },
        },
    ]

    created_tokens = []
    for token_data in tokens_data:
        # Check if token already exists
        existing_token = await Token.find_one(Token.token == token_data["token"])
        if existing_token:
            print(f"  Token for {token_data['identifier']} already exists, skipping...")
            created_tokens.append(existing_token)
        else:
            token = Token(**token_data)
            await token.insert()
            created_tokens.append(token)
            print(f"  Created token: {token_data['type']} for {token_data['identifier']}")

    return created_tokens


async def seed_mcp_servers(users):
    """Seed MCP servers with different authentication methods."""
    print("Seeding MCP servers...")

    # Sample server configurations with different authentication methods
    servers_data = [
        {
            "serverName": "github-copilot",
            "author": users[0].id,  # Admin user
            "config": {
                "name": "GitHub Integration",
                "description": "GitHub repository management and code search",
                "version": "1.2.6",
                "path": "/github-copilot",
                "url": "http://localhost:3001",
                "transport": "streamable-http",
                "scope": "shared_app",
                "status": "active",
                "authentication": {
                    "type": "oauth",
                    "provider": "github",
                    "scopes": ["repo", "read:user", "read:org", "get_pull_requests"],
                    "token_url": "https://github.com/login/oauth/access_token",
                    "authorize_url": "https://github.com/login/oauth/authorize",
                    "client_id": "7x23l1dGc5dy1s3Y-2sI",
                    "client_secret": "hc3i0fc68e0a9eece6ad4110574f797b894cba"  # Will be encrypted
                },
                "capabilities": ["create_issue", "list_repos", "search_code", "get_pull_requests"],
                "tags": ["github", "oauth", "code", "vcs"],
                "num_tools": 4,
                "supported_transports": ["streamable-http"],
                "requires_oauth": True,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "tavilysearchv1",
            "author": users[1].id,  # John Developer
            "config": {
                "title": "tavilysearchv1",
                "description": "tavily search 1",
                "path": "/tavilysearch",
                "url": "https://mcp.tavily.com/mcp/",
                "type": "streamable-http",
                "scope": "shared_user",
                "status": "active",
                "apiKey": {
                    "source": "admin",
                    "authorization_type": "custom",
                    "custom_header": "tavilyApiKey",
                    "key": "ea2ea0ba31151267149220601bd4299dfe09eccf2c4d51f3026b396fe5881a77610b...",  # Will be encrypted
                },
                "requires_oauth": False,
                "capabilities": {
                    "experimental": {},
                    "prompts": {"listChanged": True},
                    "resources": {"subscribe": True, "listChanged": True},
                },
                "tool_instructions": "tavily_search, tavily_extract, tavily_crawl, tavily_map",
                "init_duration": 170,
                "tags": ["search", "api-key", "tavily"],
                "num_tools": 4,
                "supported_transports": ["streamable-http"],
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "slack-notifications",
            "author": users[1].id,  # John Developer
            "config": {
                "name": "Slack Notifications",
                "description": "Send notifications and messages to Slack channels",
                "version": "1.5.2",
                "path": "/slack",
                "url": "http://slack-server:8012",
                "transport": "streamable-http",
                "scope": "shared_user",
                "status": "active",
                "authentication": {
                    "type": "oauth",
                    "provider": "slack",
                    "scopes": ["chat:write", "channels:read", "users:read"],
                    "token_url": "https://slack.com/api/oauth.v2.access",
                    "authorize_url": "https://slack.com/oauth/v2/authorize",
                    "client_id": "slack_client_123",
                    "client_secret": "slack_secret_xyz789",  # Will be encrypted
                },
                "capabilities": ["send_message", "list_channels", "get_user_info"],
                "tags": ["slack", "oauth", "notifications", "collaboration"],
                "num_tools": 3,
                "supported_transports": ["streamable-http"],
                "requires_oauth": True,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "weather-service",
            "author": users[2].id,  # Jane Smith
            "config": {
                "name": "Weather Service",
                "description": "Real-time weather data and forecasts",
                "version": "1.0.0",
                "path": "/weather",
                "url": "http://weather-server:8010",
                "transport": "streamable-http",
                "scope": "private_user",
                "status": "active",
                "apiKey": {
                    "source": "user",
                    "authorization_type": "custom",
                    "custom_header": "X-Weather-API-Key",
                    "key": "weather_api_key_abc123xyz456789",  # Will be encrypted
                },
                "capabilities": ["get_weather", "get_forecast", "get_alerts"],
                "tags": ["weather", "api-key", "data"],
                "num_tools": 3,
                "supported_transports": ["streamable-http"],
                "requires_oauth": False,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "public-api-service",
            "author": users[3].id,  # OAuth User
            "config": {
                "name": "Public API Service",
                "description": "Public API service with no authentication required",
                "version": "2.0.0",
                "path": "/public-api",
                "url": "http://public-api-server:8015",
                "transport": "streamable-http",
                "scope": "shared_app",
                "status": "active",
                "authentication": {
                    "type": "auto"
                },
                "capabilities": [
                    "get_public_data",
                    "search_content",
                    "get_stats",
                ],
                "tags": ["public", "no-auth", "api", "open"],
                "num_tools": 3,
                "supported_transports": ["streamable-http"],
                "requires_oauth": False,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "google-workspace",
            "author": users[3].id,  # OAuth User
            "config": {
                "name": "Google Workspace",
                "description": "Google Drive, Docs, Sheets, and Calendar integration",
                "version": "1.8.0",
                "path": "/google-workspace",
                "url": "http://google-workspace-server:8014",
                "transport": "streamable-http",
                "scope": "private_user",
                "status": "active",
                "authentication": {
                    "type": "oauth",
                    "provider": "google",
                    "scopes": [
                        "https://www.googleapis.com/auth/drive",
                        "https://www.googleapis.com/auth/documents",
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/calendar",
                    ],
                    "token_url": "https://oauth2.googleapis.com/token",
                    "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                    "client_id": "google_client_12345",
                    "client_secret": "google_secret_abc789xyz",  # Will be encrypted
                },
                "capabilities": [
                    "list_files",
                    "create_document",
                    "read_sheet",
                    "schedule_event",
                ],
                "tags": ["google", "oauth", "productivity", "cloud"],
                "num_tools": 4,
                "supported_transports": ["streamable-http"],
                "requires_oauth": True,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "atlassian-jira",
            "author": users[2].id,  # Jane Smith
            "config": {
                "name": "Atlassian JIRA",
                "description": "JIRA issue tracking and project management",
                "version": "1.2.0",
                "path": "/jira",
                "url": "http://atlassian-server:8005",
                "transport": "streamable-http",
                "scope": "shared_user",
                "status": "active",
                "authentication": {
                    "type": "oauth",
                    "provider": "atlassian",
                    "scopes": ["read:jira-work", "write:jira-work", "read:jira-user"],
                    "token_url": "https://auth.atlassian.com/oauth/token",
                    "authorize_url": "https://auth.atlassian.com/authorize",
                    "client_id": "jira_client_456",
                    "client_secret": "jira_secret_def456uvw",  # Will be encrypted
                },
                "capabilities": [
                    "create_issue",
                    "update_issue",
                    "search_issues",
                    "get_project",
                ],
                "tags": ["atlassian", "jira", "oauth", "project-management"],
                "num_tools": 4,
                "supported_transports": ["streamable-http"],
                "requires_oauth": True,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
        {
            "serverName": "currenttime-server",
            "author": users[0].id,  # Admin user
            "config": {
                "name": "Current Time Server",
                "description": "Get current time in various formats and timezones",
                "version": "1.0.0",
                "path": "/time",
                "url": "http://currenttime-server:8000",
                "transport": "streamable-http",
                "scope": "shared_app",
                "status": "active",
                "authentication": {
                    "type": "auto"
                },
                "capabilities": ["get_time", "get_timezone", "convert_time"],
                "tags": ["time", "utility", "no-auth"],
                "num_tools": 3,
                "supported_transports": ["streamable-http"],
                "requires_oauth": False,
            },
            "createdAt": datetime.now(timezone.utc),
            "updatedAt": datetime.now(timezone.utc),
        },
    ]

    created_servers = []
    for server_data in servers_data:
        # Check if server already exists
        existing_server = await MCPServerDocument.find_one(
            MCPServerDocument.serverName == server_data["serverName"]
        )
        if existing_server:
            print(f"  Server {server_data['serverName']} already exists, skipping...")
            created_servers.append(existing_server)
        else:
            # Encrypt sensitive authentication fields before storing
            server_data["config"] = encrypt_auth_fields(server_data["config"])
            
            server = MCPServerDocument(**server_data)
            await server.insert()
            created_servers.append(server)
            
            # Determine auth type for logging
            auth_type = "none"
            if "authentication" in server_data["config"]:
                auth_type = server_data["config"]["authentication"].get("type", "none")
            elif "apiKey" in server_data["config"]:
                auth_type = "apiKey"
            
            print(f"  Created server: {server_data['serverName']} (auth: {auth_type})")

    return created_servers


async def clean_database():
    """Clean all seeded collections."""
    print("Cleaning database collections...")

    try:
        # Delete all documents from each collection
        user_count = await IUser.delete_all()
        print(f"  Deleted {user_count.deleted_count} users")

        key_count = await Key.delete_all()
        print(f"  Deleted {key_count.deleted_count} keys")

        token_count = await Token.delete_all()
        print(f"  Deleted {token_count.deleted_count} tokens")

        server_count = await MCPServerDocument.delete_all()
        print(f"  Deleted {server_count.deleted_count} MCP servers")

        print("\n" + "=" * 60)
        print("✅ Database cleaned successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error cleaning database: {e}")
        raise


async def main():
    """Main function to seed or clean data."""
    # Parse command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else "seed"

    if command not in ["seed", "clean"]:
        print(f"❌ Unknown command: {command}")
        print("\nUsage:")
        print("  python scripts/seed_mongodb.py          # Seed data (default)")
        print("  python scripts/seed_mongodb.py seed     # Seed data")
        print("  python scripts/seed_mongodb.py clean    # Clean all collections")
        sys.exit(1)

    # Get MongoDB connection details from environment
    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/jarvis")

    # Parse database name from URI if present
    db_name = None
    if '/' in mongo_uri.split('://')[-1]:
        # Extract database name from URI (everything after the last /)
        uri_path = mongo_uri.split('://')[-1]
        if '/' in uri_path:
            db_name = uri_path.split('/')[-1].split('?')[0]  # Handle query params

    # Fall back to default if not in URI
    if not db_name:
        db_name = "jarvis"

    print(f"Connecting to MongoDB at {mongo_uri}...")
    print(f"Database: {db_name}")
    print(f"Command: {command}\n")

    try:
        # Connect to MongoDB
        await MongoDB.connect_db(db_name=db_name)
        print("Connected to MongoDB successfully!\n")

        if command == "clean":
            # Clean database
            await clean_database()
        else:
            # Seed data in order
            users = await seed_users()
            print()

            keys = await seed_keys(users)
            print()

            tokens = await seed_tokens(users)
            print()

            servers = await seed_mcp_servers(users)
            print()

            print("=" * 60)
            print("✅ Database seeding completed successfully!")
            print("=" * 60)
            print(f"Created/Found:")
            print(f"  - {len(users)} users")
            print(f"  - {len(keys)} API keys")
            print(f"  - {len(tokens)} tokens")
            print(f"  - {len(servers)} MCP servers")
            print(
                f"    • API Key auth: {sum(1 for s in servers if s.config.get('authentication', {}).get('type') == 'api_key')}")
            print(
                f"    • OAuth auth: {sum(1 for s in servers if s.config.get('authentication', {}).get('type') == 'oauth')}")
            print(
                f"    • No auth: {sum(1 for s in servers if s.config.get('authentication', {}).get('type') == 'none')}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Close connection
        await MongoDB.close_db()
        print("\nMongoDB connection closed.")


def cli():
    """Entry point for command-line script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()

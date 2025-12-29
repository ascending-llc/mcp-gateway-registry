#!/usr/bin/env python3
"""
CLI Wrapper for Registry Management API

This module provides a command-line interface that wraps the Registry Management API,
maintaining backwards compatibility with the deprecated shell scripts while using
the modern Python API underneath.

This wrapper is designed to be called from the TypeScript CLI application via subprocess.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path to import registry_client
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.registry_client import RegistryClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


def _load_token_from_file(
    token_file: str,
) -> str:
    """Load access token from JSON file.

    Args:
        token_file: Path to token file containing access_token field

    Returns:
        Access token string
    """
    with open(token_file, 'r') as f:
        token_data = json.load(f)
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(f"No access_token found in {token_file}")
    return access_token


def _get_registry_client(
    base_url: str,
    token_file: Optional[str] = None,
) -> RegistryClient:
    """Create and return a configured RegistryClient.

    Args:
        base_url: Registry base URL
        token_file: Optional path to token file

    Returns:
        Configured RegistryClient instance
    """
    if token_file:
        access_token = _load_token_from_file(token_file)
    else:
        # Try to get from environment
        access_token = os.getenv("GATEWAY_TOKEN")
        if not access_token:
            raise ValueError("No token provided via --token-file or GATEWAY_TOKEN env var")

    return RegistryClient(registry_url=base_url, token=access_token)


def _print_json_response(
    data: Any,
) -> None:
    """Pretty-print JSON response.

    Args:
        data: Data to print as JSON
    """
    print(json.dumps(data, indent=2, default=str))


def _handle_service_add(
    args: argparse.Namespace,
) -> None:
    """Handle service add command."""
    client = _get_registry_client(args.base_url, args.token_file)

    # Load config from file
    with open(args.config_path, 'r') as f:
        config = json.load(f)

    result = client.register_server(config)
    _print_json_response(result.model_dump())


def _handle_service_delete(
    args: argparse.Namespace,
) -> None:
    """Handle service delete command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.remove_server(args.path, force=True)
    _print_json_response(result.model_dump())


def _handle_service_list(
    args: argparse.Namespace,
) -> None:
    """Handle service list command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.anthropic_list_servers(limit=1000)
    _print_json_response(result.model_dump())


def _handle_service_monitor(
    args: argparse.Namespace,
) -> None:
    """Handle service monitor command."""
    # Monitor is essentially list with detailed output
    _handle_service_list(args)


def _handle_group_create(
    args: argparse.Namespace,
) -> None:
    """Handle group create command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.group_create(
        name=args.name,
        description=args.description
    )
    _print_json_response(result.model_dump())


def _handle_group_delete(
    args: argparse.Namespace,
) -> None:
    """Handle group delete command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.group_delete(name=args.name, force=True)
    _print_json_response(result.model_dump())


def _handle_group_list(
    args: argparse.Namespace,
) -> None:
    """Handle group list command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.group_list()
    _print_json_response(result)


def _handle_user_create_m2m(
    args: argparse.Namespace,
) -> None:
    """Handle M2M user creation command."""
    client = _get_registry_client(args.base_url, args.token_file)

    groups = args.groups.split(',') if args.groups else []

    result = client.user_create_m2m(
        name=args.name,
        groups=groups,
        description=args.description
    )
    _print_json_response(result.model_dump())


def _handle_user_create_human(
    args: argparse.Namespace,
) -> None:
    """Handle human user creation command."""
    client = _get_registry_client(args.base_url, args.token_file)

    groups = args.groups.split(',') if args.groups else []

    result = client.user_create_human(
        username=args.username,
        email=args.email,
        first_name=args.first_name,
        last_name=args.last_name,
        groups=groups,
        password=args.password
    )
    _print_json_response(result.model_dump())


def _handle_user_delete(
    args: argparse.Namespace,
) -> None:
    """Handle user delete command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.user_delete(username=args.username, force=True)
    _print_json_response(result.model_dump())


def _handle_user_list(
    args: argparse.Namespace,
) -> None:
    """Handle user list command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.user_list()
    _print_json_response(result)


def _handle_anthropic_list(
    args: argparse.Namespace,
) -> None:
    """Handle Anthropic API list command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.anthropic_list_servers(limit=args.limit if hasattr(args, 'limit') else 100)
    _print_json_response(result.model_dump())


def _handle_anthropic_get(
    args: argparse.Namespace,
) -> None:
    """Handle Anthropic API get command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.anthropic_get_server(server_name=args.server_name)
    _print_json_response(result.model_dump())


def _handle_agent_list(
    args: argparse.Namespace,
) -> None:
    """Handle agent list command."""
    client = _get_registry_client(args.base_url, args.token_file)

    query = args.query if hasattr(args, 'query') else None
    enabled_only = args.enabled_only if hasattr(args, 'enabled_only') else False

    result = client.list_agents(query=query, enabled_only=enabled_only)
    _print_json_response(result.model_dump())


def _handle_agent_get(
    args: argparse.Namespace,
) -> None:
    """Handle agent get command."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.get_agent(path=args.path)
    _print_json_response(result.model_dump())


def _handle_agent_search(
    args: argparse.Namespace,
) -> None:
    """Handle agent search command (alias for list with query)."""
    client = _get_registry_client(args.base_url, args.token_file)

    result = client.list_agents(query=args.query, enabled_only=False)
    _print_json_response(result.model_dump())


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Registry Management CLI Wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--base-url",
        default=os.getenv("GATEWAY_BASE_URL", "http://localhost"),
        help="Registry base URL (default: http://localhost)"
    )

    parser.add_argument(
        "--token-file",
        help="Path to token file containing access_token"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Service management commands
    service_parser = subparsers.add_parser("service", help="Service management commands")
    service_subparsers = service_parser.add_subparsers(dest="subcommand")

    # Service add
    add_parser = service_subparsers.add_parser("add", help="Add a service")
    add_parser.add_argument("config_path", help="Path to service config JSON file")

    # Service delete
    delete_parser = service_subparsers.add_parser("delete", help="Delete a service")
    delete_parser.add_argument("path", help="Service path")

    # Service list
    service_subparsers.add_parser("list", help="List services")

    # Service monitor
    service_subparsers.add_parser("monitor", help="Monitor services")

    # Group management commands
    group_parser = subparsers.add_parser("group", help="Group management commands")
    group_subparsers = group_parser.add_subparsers(dest="subcommand")

    # Group create
    group_create_parser = group_subparsers.add_parser("create", help="Create a group")
    group_create_parser.add_argument("--name", required=True, help="Group name")
    group_create_parser.add_argument("--description", help="Group description")

    # Group delete
    group_delete_parser = group_subparsers.add_parser("delete", help="Delete a group")
    group_delete_parser.add_argument("--name", required=True, help="Group name")

    # Group list
    group_subparsers.add_parser("list", help="List groups")

    # User management commands
    user_parser = subparsers.add_parser("user", help="User management commands")
    user_subparsers = user_parser.add_subparsers(dest="subcommand")

    # User create M2M
    m2m_parser = user_subparsers.add_parser("create-m2m", help="Create M2M user")
    m2m_parser.add_argument("--name", required=True, help="Service account name")
    m2m_parser.add_argument("--groups", help="Comma-separated list of groups")
    m2m_parser.add_argument("--description", help="Service account description")

    # User create human
    human_parser = user_subparsers.add_parser("create-human", help="Create human user")
    human_parser.add_argument("--username", required=True, help="Username")
    human_parser.add_argument("--email", required=True, help="Email address")
    human_parser.add_argument("--first-name", required=True, help="First name")
    human_parser.add_argument("--last-name", required=True, help="Last name")
    human_parser.add_argument("--groups", help="Comma-separated list of groups")
    human_parser.add_argument("--password", required=True, help="Password")

    # User delete
    user_delete_parser = user_subparsers.add_parser("delete", help="Delete user")
    user_delete_parser.add_argument("--username", required=True, help="Username")

    # User list
    user_subparsers.add_parser("list", help="List users")

    # Anthropic API commands
    anthropic_parser = subparsers.add_parser("anthropic", help="Anthropic API commands")
    anthropic_subparsers = anthropic_parser.add_subparsers(dest="subcommand")

    # Anthropic list
    list_parser = anthropic_subparsers.add_parser("list", help="List servers (Anthropic API)")
    list_parser.add_argument("--limit", type=int, default=100, help="Limit results")

    # Anthropic get
    get_parser = anthropic_subparsers.add_parser("get", help="Get server details (Anthropic API)")
    get_parser.add_argument("server_name", help="Server name")

    # Agent management commands
    agent_parser = subparsers.add_parser("agent", help="Agent management commands")
    agent_subparsers = agent_parser.add_subparsers(dest="subcommand")

    # Agent list
    agent_list_parser = agent_subparsers.add_parser("list", help="List agents")
    agent_list_parser.add_argument("--query", help="Search query")
    agent_list_parser.add_argument("--enabled-only", action="store_true", help="Show only enabled agents")

    # Agent get
    agent_get_parser = agent_subparsers.add_parser("get", help="Get agent details")
    agent_get_parser.add_argument("path", help="Agent path")

    # Agent search
    agent_search_parser = agent_subparsers.add_parser("search", help="Search agents")
    agent_search_parser.add_argument("query", help="Search query")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        # Route to appropriate handler
        if args.command == "service":
            if args.subcommand == "add":
                _handle_service_add(args)
            elif args.subcommand == "delete":
                _handle_service_delete(args)
            elif args.subcommand == "list":
                _handle_service_list(args)
            elif args.subcommand == "monitor":
                _handle_service_monitor(args)
            else:
                service_parser.print_help()
                sys.exit(1)

        elif args.command == "group":
            if args.subcommand == "create":
                _handle_group_create(args)
            elif args.subcommand == "delete":
                _handle_group_delete(args)
            elif args.subcommand == "list":
                _handle_group_list(args)
            else:
                group_parser.print_help()
                sys.exit(1)

        elif args.command == "user":
            if args.subcommand == "create-m2m":
                _handle_user_create_m2m(args)
            elif args.subcommand == "create-human":
                _handle_user_create_human(args)
            elif args.subcommand == "delete":
                _handle_user_delete(args)
            elif args.subcommand == "list":
                _handle_user_list(args)
            else:
                user_parser.print_help()
                sys.exit(1)

        elif args.command == "anthropic":
            if args.subcommand == "list":
                _handle_anthropic_list(args)
            elif args.subcommand == "get":
                _handle_anthropic_get(args)
            else:
                anthropic_parser.print_help()
                sys.exit(1)

        elif args.command == "agent":
            if args.subcommand == "list":
                _handle_agent_list(args)
            elif args.subcommand == "get":
                _handle_agent_get(args)
            elif args.subcommand == "search":
                _handle_agent_search(args)
            else:
                agent_parser.print_help()
                sys.exit(1)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        logger.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

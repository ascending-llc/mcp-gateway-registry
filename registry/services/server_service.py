import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from ..core.config import settings

logger = logging.getLogger(__name__)


class ServerService:
    """Service for managing server registration and state."""
    
    def __init__(self):
        self.registered_servers: Dict[str, Dict[str, Any]] = {}
        self.service_state: Dict[str, bool] = {}  # enabled/disabled state
        
    def load_servers_and_state(self):
        """Load server definitions and persisted state from disk."""
        logger.info(f"Loading server definitions from {settings.servers_dir}...")
        
        # Create servers directory if it doesn't exist
        settings.servers_dir.mkdir(parents=True, exist_ok=True)
        
        temp_servers = {}
        server_files = list(settings.servers_dir.glob("**/*.json"))
        logger.info(f"Found {len(server_files)} JSON files in {settings.servers_dir} and its subdirectories")
        
        for file in server_files:
            logger.info(f"[DEBUG] - {file.relative_to(settings.servers_dir)}")
        
        if not server_files:
            logger.warning(f"No server definition files found in {settings.servers_dir}. Initializing empty registry.")
            self.registered_servers = {}
        
        for server_file in server_files:
            if server_file.name == settings.state_file_path.name:  # Skip the state file itself
                continue
                
            try:
                with open(server_file, "r") as f:
                    server_info = json.load(f)
                    
                    if (
                        isinstance(server_info, dict)
                        and "path" in server_info
                        and "server_name" in server_info
                    ):
                        server_path = server_info["path"]
                        if server_path in temp_servers:
                            logger.warning(f"Duplicate server path found in {server_file}: {server_path}. Overwriting previous definition.")
                        
                        # Add default fields
                        server_info["description"] = server_info.get("description", "")
                        server_info["tags"] = server_info.get("tags", [])
                        server_info["num_tools"] = server_info.get("num_tools", 0)
                        server_info["num_stars"] = server_info.get("num_stars", 0)
                        server_info["is_python"] = server_info.get("is_python", False)
                        server_info["license"] = server_info.get("license", "N/A")
                        server_info["proxy_pass_url"] = server_info.get("proxy_pass_url", None)
                        server_info["tool_list"] = server_info.get("tool_list", [])
                        
                        temp_servers[server_path] = server_info
                    else:
                        logger.warning(f"Invalid server entry format found in {server_file}. Skipping.")
            except FileNotFoundError:
                logger.error(f"Server definition file {server_file} reported by glob not found.")
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse JSON from {server_file}: {e}.")
            except Exception as e:
                logger.error(f"An unexpected error occurred loading {server_file}: {e}", exc_info=True)
        
        self.registered_servers = temp_servers
        logger.info(f"Successfully loaded {len(self.registered_servers)} server definitions.")
        
        # Load persisted service state
        self._load_service_state()
        
    def _load_service_state(self):
        """Load persisted service state from disk."""
        logger.info(f"Attempting to load persisted state from {settings.state_file_path}...")
        loaded_state = {}
        
        try:
            if settings.state_file_path.exists():
                with open(settings.state_file_path, "r") as f:
                    loaded_state = json.load(f)
                if not isinstance(loaded_state, dict):
                    logger.warning(f"Invalid state format in {settings.state_file_path}. Expected a dictionary. Resetting state.")
                    loaded_state = {}
                else:
                    logger.info("Successfully loaded persisted state.")
            else:
                logger.info(f"No persisted state file found at {settings.state_file_path}. Initializing state.")
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from {settings.state_file_path}: {e}. Initializing empty state.")
            loaded_state = {}
        except Exception as e:
            logger.error(f"Failed to read state file {settings.state_file_path}: {e}. Initializing empty state.", exc_info=True)
            loaded_state = {}
        
        # Initialize service state
        self.service_state = {}
        for path in self.registered_servers.keys():
            # Try exact match first, then try with/without trailing slash
            value = loaded_state.get(path, None)
            if value is None:
                if path.endswith('/'):
                    # Try without trailing slash
                    value = loaded_state.get(path.rstrip('/'), False)
                else:
                    # Try with trailing slash
                    value = loaded_state.get(path + '/', False)
            self.service_state[path] = value
        
        logger.info(f"Initial service state loaded: {self.service_state}")
        
    def save_service_state(self):
        """Persist service state to disk."""
        try:
            with open(settings.state_file_path, "w") as f:
                json.dump(self.service_state, f, indent=2)
            logger.info(f"Persisted state to {settings.state_file_path}")
        except Exception as e:
            logger.error(f"ERROR: Failed to persist state to {settings.state_file_path}: {e}")
            
    def save_server_to_file(self, server_info: Dict[str, Any]) -> bool:
        """Save server data to individual file."""
        try:
            # Create servers directory if it doesn't exist
            settings.servers_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename based on path
            path = server_info["path"]
            filename = self._path_to_filename(path)
            file_path = settings.servers_dir / filename
            
            with open(file_path, "w") as f:
                json.dump(server_info, f, indent=2)
            
            logger.info(f"Successfully saved server '{server_info['server_name']}' to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save server '{server_info.get('server_name', 'UNKNOWN')}' data to {filename}: {e}", exc_info=True)
            return False
            
    def _path_to_filename(self, path: str) -> str:
        """Convert a path to a safe filename."""
        # Remove leading slash and replace remaining slashes with underscores
        normalized = path.lstrip("/").replace("/", "_")
        # Append .json extension if not present
        if not normalized.endswith(".json"):
            normalized += ".json"
        return normalized
        
    def register_server(self, server_info: Dict[str, Any]) -> bool:
        """Register a new server."""
        path = server_info["path"]
        
        # Check if path already exists
        if path in self.registered_servers:
            logger.error(f"Service registration failed: path '{path}' already exists")
            return False
            
        # Save to file
        if not self.save_server_to_file(server_info):
            return False
            
        # Add to in-memory registry and default to disabled
        self.registered_servers[path] = server_info
        self.service_state[path] = False
        
        # Persist state
        self.save_service_state()
        
        logger.info(f"New service registered: '{server_info['server_name']}' at path '{path}'")
        return True
        
    def update_server(self, path: str, server_info: Dict[str, Any]) -> bool:
        """Update an existing server."""
        if path not in self.registered_servers:
            logger.error(f"Cannot update server at path '{path}': not found")
            return False
            
        # Ensure path is consistent
        server_info["path"] = path
        
        # Save to file
        if not self.save_server_to_file(server_info):
            return False
            
                # Update in-memory registry
        self.registered_servers[path] = server_info
        
        logger.info(f"Server '{server_info['server_name']}' ({path}) updated")

        # Update FAISS index with new server information
        try:
            from ..search.service import faiss_service
            import asyncio

            # Check if we're in an async context
            try:
                asyncio.get_running_loop()
                # We're in an async context, schedule the update
                asyncio.create_task(faiss_service.add_or_update_service(path, server_info, self.is_service_enabled(path)))
            except RuntimeError:
                # No event loop running, we're in sync context - skip FAISS update
                # This will be handled by the caller in async context
                logger.debug(f"Skipping FAISS update for {path} - no async context available")

        except Exception as e:
            logger.error(f"Failed to update FAISS index after server update: {e}")

        # Regenerate nginx config if this is an enabled service (proxy_pass_url might have changed)
        if self.is_service_enabled(path):
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    service_path: self.get_server_info(service_path)
                    for service_path in self.get_enabled_services()
                }
                nginx_service.generate_config(enabled_servers)
                nginx_service.reload_nginx()
                logger.info(f"Regenerated nginx config due to server update: {path}")
            except Exception as e:
                logger.error(f"Failed to regenerate nginx configuration after server update: {e}")

        return True
        
    def toggle_service(self, path: str, enabled: bool) -> bool:
        """Toggle service enabled/disabled state."""
        if path not in self.registered_servers:
            logger.error(f"Cannot toggle service at path '{path}': not found")
            return False
            
        self.service_state[path] = enabled
        self.save_service_state()
        
        server_name = self.registered_servers[path]["server_name"]
        logger.info(f"Toggled '{server_name}' ({path}) to {enabled}")
        
        # Trigger nginx config regeneration and reload
        try:
            from ..core.nginx_service import nginx_service
            enabled_servers = {
                service_path: self.get_server_info(service_path) 
                for service_path in self.get_enabled_services()
            }
            nginx_service.generate_config(enabled_servers)
            nginx_service.reload_nginx()
        except Exception as e:
            logger.error(f"Failed to update nginx configuration after toggle: {e}")
        
        return True
        
    def get_server_info(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Get server information by path.

        Handles path normalization to support lookups with or without trailing slashes.
        If the exact path is not found, tries the alternate form (with/without trailing slash).

        Args:
            path: The server path to look up

        Returns:
            Server info dict if found, None otherwise
        """
        # Try exact match first
        server_info = self.registered_servers.get(path)
        if server_info:
            return server_info

        # If not found, try alternate form (add or remove trailing slash)
        if path.endswith('/'):
            alternate_path = path.rstrip('/')
        else:
            alternate_path = path + '/'

        return self.registered_servers.get(alternate_path)
        
    def get_all_servers(self, include_federated: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered servers.

        Args:
            include_federated: If True, include servers from federated registries

        Returns:
            Dict of all servers (local and federated if requested)
        """
        all_servers = self.registered_servers.copy()

        # Add federated servers if requested
        if include_federated:
            try:
                from .federation_service import get_federation_service
                federation_service = get_federation_service()
                federated_servers = federation_service.get_federated_servers()

                # Add federated servers with their paths as keys
                for fed_server in federated_servers:
                    path = fed_server.get("path")
                    if path and path not in all_servers:
                        all_servers[path] = fed_server

                logger.debug(f"Included {len(federated_servers)} federated servers")
            except Exception as e:
                logger.error(f"Failed to get federated servers: {e}")

        return all_servers
        
    def get_filtered_servers(self, accessible_servers: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get servers filtered by user's accessible servers list.
        
        Args:
            accessible_servers: List of server names the user can access
            
        Returns:
            Dict of servers the user is authorized to see
        """
        if not accessible_servers:
            logger.debug("User has no accessible servers, returning empty dict")
            return {}
        
        logger.info(f"DEBUG: get_filtered_servers called with accessible_servers: {accessible_servers}")
        logger.info(f"DEBUG: Available registered servers paths: {list(self.registered_servers.keys())}")
        
        filtered_servers = {}
        for path, server_info in self.registered_servers.items():
            server_name = server_info.get("server_name", "")
            # Extract technical name from path (remove leading and trailing slashes)
            technical_name = path.strip('/')
            logger.info(f"DEBUG: Checking server path='{path}', server_name='{server_name}', technical_name='{technical_name}' against accessible_servers")
            
            # Check if user has access to this server using technical name
            if technical_name in accessible_servers:
                filtered_servers[path] = server_info
                logger.info(f"DEBUG: ✓ User has access to server: {technical_name} ({server_name})")
            else:
                logger.info(f"DEBUG: ✗ User does not have access to server: {technical_name} ({server_name})")
        
        logger.info(f"Filtered {len(filtered_servers)} servers from {len(self.registered_servers)} total servers")
        return filtered_servers

    def get_all_servers_with_permissions(
        self,
        accessible_servers: Optional[List[str]] = None,
        include_federated: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get servers with optional filtering based on user permissions.

        Args:
            accessible_servers: Optional list of server names the user can access.
                               If None, returns all servers (admin access).
            include_federated: If True, include servers from federated registries

        Returns:
            Dict of servers the user is authorized to see
        """
        if accessible_servers is None:
            # Admin access - return all servers (including federated)
            logger.debug("Admin access - returning all servers")
            return self.get_all_servers(include_federated=include_federated)
        else:
            # Filtered access - return only accessible servers
            logger.debug(f"Filtered access - returning servers accessible to user: {accessible_servers}")
            # Note: Federated servers are read-only, so we include them in filtered results too
            all_servers = self.get_all_servers(include_federated=include_federated)

            # Filter based on accessible_servers
            filtered_servers = {}
            for path, server_info in all_servers.items():
                server_name = server_info.get("server_name", "")
                technical_name = path.strip('/')

                # Check if user has access to this server using technical name
                if technical_name in accessible_servers:
                    filtered_servers[path] = server_info

            return filtered_servers

    def user_can_access_server_path(self, path: str, accessible_servers: List[str]) -> bool:
        """
        Check if user can access a specific server by path.
        
        Args:
            path: Server path to check
            accessible_servers: List of server names the user can access
            
        Returns:
            True if user can access the server, False otherwise
        """
        server_info = self.get_server_info(path)
        if not server_info:
            return False

        # Extract technical name from path (remove leading and trailing slashes)
        technical_name = path.strip('/')
        return technical_name in accessible_servers

    def is_service_enabled(self, path: str) -> bool:
        """Check if a service is enabled."""
        # Try exact match first
        result = self.service_state.get(path, None)
        
        # If no exact match, try with/without trailing slash
        if result is None:
            if path.endswith('/'):
                # Try without trailing slash
                result = self.service_state.get(path.rstrip('/'), False)
            else:
                # Try with trailing slash
                result = self.service_state.get(path + '/', False)
        
        if result is None:
            result = False
            
        logger.info(f"[SERVER_DEBUG] is_service_enabled({path}) -> service_state: {self.service_state}, result: {result}")
        return result
        
    def get_enabled_services(self) -> List[str]:
        """Get list of enabled service paths."""
        return [path for path, enabled in self.service_state.items() if enabled]

    def reload_state_from_disk(self):
        """Reload service state from disk (useful when state file is modified externally)."""
        logger.info("Reloading service state from disk...")
        
        # Store previous state to detect changes
        previous_enabled_services = set(self.get_enabled_services())
        
        self._load_service_state()
        
        # Check if enabled services changed
        current_enabled_services = set(self.get_enabled_services())
        
        if previous_enabled_services != current_enabled_services:
            logger.info(f"Service state changes detected: {len(previous_enabled_services)} -> {len(current_enabled_services)} enabled services")
            
            # Regenerate nginx configuration due to state changes
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    service_path: self.get_server_info(service_path) 
                    for service_path in self.get_enabled_services()
                }
                nginx_service.generate_config(enabled_servers)
                nginx_service.reload_nginx()
                logger.info("Regenerated nginx config due to state reload")
            except Exception as e:
                logger.error(f"Failed to regenerate nginx configuration after state reload: {e}")
        else:
            logger.info("No service state changes detected after reload")


    def update_rating(
        self,
        path: str,
        username: str,
        rating: int,
    ) -> float:
        """
        Log a user rating for a server. If the user has already rated, update their rating.

        Args:
            path: server path
            username: The user who submitted rating
            rating: integer between 1-5

        Return:
            Updated average rating

        Raises:
            ValueError: If server not found or invalid rating
        """
        from . import rating_service

        if path not in self.registered_servers:
            logger.error(f"Cannot update server at path '{path}': not found")
            raise ValueError(f"Server not found at path: {path}")

        # Validate rating using shared service
        rating_service.validate_rating(rating)

        server_info = self.registered_servers[path]

        # Ensure rating_details is a list
        if "rating_details" not in server_info or server_info["rating_details"] is None:
            server_info["rating_details"] = []

        # Update rating details using shared service
        updated_details, is_new_rating = rating_service.update_rating_details(
            server_info["rating_details"],
            username,
            rating
        )
        server_info["rating_details"] = updated_details

        # Calculate average rating using shared service
        server_info["num_stars"] = rating_service.calculate_average_rating(
            server_info["rating_details"]
        )

        # Save to file
        self.save_server_to_file(server_info)

        logger.info(
            f"Updated rating for server {path}: user {username} rated {rating}, "
            f"new average: {server_info['num_stars']:.2f}"
        )
        return server_info["num_stars"]

    def remove_server(self, path: str) -> bool:
        """Remove a server from the registry and file system."""
        # Check if server exists
        if path not in self.registered_servers:
            logger.error(f"Cannot remove server at path '{path}': not found in registry")
            return False

        try:
            # Remove from file system
            filename = self._path_to_filename(path)
            file_path = settings.servers_dir / filename

            if file_path.exists():
                file_path.unlink()
                logger.info(f"Removed server file: {file_path}")
            else:
                logger.warning(f"Server file not found: {file_path}")

            # Remove from in-memory registry
            server_name = self.registered_servers[path].get('server_name', 'Unknown')
            del self.registered_servers[path]

            # Remove from service state
            if path in self.service_state:
                del self.service_state[path]

            # Persist updated state
            self.save_service_state()

            logger.info(f"Successfully removed server '{server_name}' from path '{path}'")
            return True

        except Exception as e:
            logger.error(f"Failed to remove server at path '{path}': {e}", exc_info=True)
            return False


# Global service instance
server_service = ServerService() 
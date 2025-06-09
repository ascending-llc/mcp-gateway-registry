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
            self.service_state[path] = loaded_state.get(path, False)
        
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
        """Get server information by path."""
        return self.registered_servers.get(path)
        
    def get_all_servers(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered servers."""
        return self.registered_servers.copy()
        
    def is_service_enabled(self, path: str) -> bool:
        """Check if a service is enabled."""
        result = self.service_state.get(path, False)
        logger.info(f"[SERVER_DEBUG] is_service_enabled({path}) -> service_state: {self.service_state}, result: {result}")
        return result
        
    def get_enabled_services(self) -> List[str]:
        """Get list of enabled service paths."""
        return [path for path, enabled in self.service_state.items() if enabled]

    def reload_state_from_disk(self):
        """Reload service state from disk (useful when state file is modified externally)."""
        logger.info("Reloading service state from disk...")
        self._load_service_state()


# Global service instance
server_service = ServerService() 
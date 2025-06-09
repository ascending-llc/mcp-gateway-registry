import logging
from pathlib import Path
from typing import Dict, Any

from .config import settings

logger = logging.getLogger(__name__)


class NginxConfigService:
    """Service for generating Nginx configuration for registered servers."""
    
    def __init__(self):
        self.nginx_template_path = settings.container_registry_dir / "nginx_template.conf"
        
    def generate_config(self, servers: Dict[str, Dict[str, Any]]) -> bool:
        """Generate Nginx configuration file based on registered servers.
        
        Only includes enabled servers that are healthy in the configuration.
        """
        try:
            # Read template
            if not self.nginx_template_path.exists():
                logger.warning(f"Nginx template not found at {self.nginx_template_path}")
                return False
                
            with open(self.nginx_template_path, "r") as f:
                template_content = f.read()
            
            # Get health service to check server health
            from ..health.service import health_service
            
            # Generate location blocks for enabled and healthy servers only
            location_blocks = []
            for path, server_info in servers.items():
                proxy_pass_url = server_info.get("proxy_pass_url")
                if proxy_pass_url:
                    # Check if server is healthy
                    health_status = health_service.server_health_status.get(path, "unknown")
                    
                    if health_status == "healthy":
                        location_block = f"""
    location {path}/ {{
        # Capture request body for auth validation using Lua
        rewrite_by_lua_file /etc/nginx/lua/capture_body.lua;
        
        # Authenticate request - pass entire request to auth server
        auth_request /validate;
        
        # Proxy to MCP server
        proxy_pass {proxy_pass_url};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add original URL for auth server scope validation
        proxy_set_header X-Original-URL $scheme://$host$request_uri;
        
        # Pass through the original authentication headers
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-User-Pool-Id $http_x_user_pool_id;
        proxy_set_header X-Client-Id $http_x_client_id;
        proxy_set_header X-Region $http_x_region;
        
        # For SSE connections and WebSocket upgrades
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection $http_connection;
        proxy_set_header Upgrade $http_upgrade;
        chunked_transfer_encoding off;
        
        # Handle auth errors
        error_page 401 = @auth_error;
        error_page 403 = @forbidden_error;
    }}"""
                        location_blocks.append(location_block)
                        logger.debug(f"Added location block for healthy service: {path}")
                    else:
                        # Add commented out block for unhealthy services
                        commented_block = f"""
#    location {path}/ {{
#        # Service currently unhealthy (status: {health_status})
#        # Proxy to MCP server
#        proxy_pass {proxy_pass_url};
#        proxy_http_version 1.1;
#        proxy_set_header Host $host;
#        proxy_set_header X-Real-IP $remote_addr;
#        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#        proxy_set_header X-Forwarded-Proto $scheme;
#    }}"""
                        location_blocks.append(commented_block)
                        logger.debug(f"Added commented location block for unhealthy service {path} (status: {health_status})")
            
            # Replace placeholder in template
            config_content = template_content.replace("{{LOCATION_BLOCKS}}", "\n".join(location_blocks))
            
            # Write config file
            with open(settings.nginx_config_path, "w") as f:
                f.write(config_content)
                
            logger.info(f"Generated Nginx configuration with {len(location_blocks)} healthy location blocks")
            
            # Automatically reload nginx after generating config
            self.reload_nginx()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate Nginx configuration: {e}", exc_info=True)
            return False
            
    def reload_nginx(self) -> bool:
        """Reload Nginx configuration (if running in appropriate environment)."""
        try:
            import subprocess
            result = subprocess.run(["nginx", "-s", "reload"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Nginx configuration reloaded successfully")
                return True
            else:
                logger.error(f"Failed to reload Nginx: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.warning("Nginx not found - skipping reload")
            return False
        except Exception as e:
            logger.error(f"Error reloading Nginx: {e}")
            return False


# Global nginx service instance
nginx_service = NginxConfigService() 
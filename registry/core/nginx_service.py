import logging
import asyncio
import httpx
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .config import settings
from registry.constants import HealthStatus, REGISTRY_CONSTANTS

logger = logging.getLogger(__name__)


class NginxConfigService:
    """Service for generating Nginx configuration for registered servers."""

    def __init__(self):
        # Determine which template to use based on SSL certificate availability
        ssl_cert_path = Path(REGISTRY_CONSTANTS.SSL_CERT_PATH)
        ssl_key_path = Path(REGISTRY_CONSTANTS.SSL_KEY_PATH)

        # Check if SSL certificates exist
        if ssl_cert_path.exists() and ssl_key_path.exists():
            # Use HTTP + HTTPS template
            if Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_AND_HTTPS).exists():
                self.nginx_template_path = Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_AND_HTTPS)
            else:
                # Fallback for local development
                self.nginx_template_path = Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_AND_HTTPS_LOCAL)
        else:
            # Use HTTP-only template
            if Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_ONLY).exists():
                self.nginx_template_path = Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_ONLY)
            else:
                # Fallback for local development
                self.nginx_template_path = Path(REGISTRY_CONSTANTS.NGINX_TEMPLATE_HTTP_ONLY_LOCAL)
        
    async def get_ec2_public_dns(self) -> str:
        """Fetch EC2 public DNS from metadata service."""
        try:
            # EC2 Instance Metadata Service v2 (IMDSv2) 
            # First get session token
            async with httpx.AsyncClient() as client:
                # Get session token
                token_response = await client.put(
                    "http://169.254.169.254/latest/api/token",
                    headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
                    timeout=2.0
                )
                
                if token_response.status_code == 200:
                    token = token_response.text
                    
                    # Get public hostname using the token
                    dns_response = await client.get(
                        "http://169.254.169.254/latest/meta-data/public-hostname",
                        headers={"X-aws-ec2-metadata-token": token},
                        timeout=2.0
                    )
                    
                    if dns_response.status_code == 200:
                        public_dns = dns_response.text.strip()
                        logger.info(f"Successfully fetched EC2 public DNS: {public_dns}")
                        return public_dns
                    else:
                        logger.warning(f"Failed to get public hostname: HTTP {dns_response.status_code}")
                else:
                    logger.warning(f"Failed to get metadata token: HTTP {token_response.status_code}")
                    
        except httpx.TimeoutException:
            logger.warning("Timeout while fetching EC2 metadata - likely not running on EC2")
        except httpx.ConnectError:
            logger.warning("Cannot connect to EC2 metadata service - likely not running on EC2")
        except Exception as e:
            logger.warning(f"Error fetching EC2 public DNS: {e}")
            
        # Fallback: try environment variable or return empty string
        import os
        fallback_dns = os.environ.get('EC2_PUBLIC_DNS', '')
        if fallback_dns:
            logger.info(f"Using EC2_PUBLIC_DNS environment variable: {fallback_dns}")
            return fallback_dns
        
        logger.info("No EC2 public DNS available, using empty string")
        return ""

    def generate_config(self, servers: Dict[str, Dict[str, Any]]) -> bool:
        """Generate Nginx configuration (synchronous version for non-async contexts)."""
        try:
            # Check if we're in an async context
            try:
                # If we're already in an event loop, we need to run this differently
                loop = asyncio.get_running_loop()
                # We're in an async context, this won't work
                logger.error("generate_config called from async context - use generate_config_async instead")
                return False
            except RuntimeError:
                # No running loop, we can use asyncio.run()
                return asyncio.run(self.generate_config_async(servers))
        except Exception as e:
            logger.error(f"Failed to generate Nginx configuration: {e}", exc_info=True)
            return False
        
    async def generate_config_async(self, servers: Dict[str, Dict[str, Any]]) -> bool:
        """Generate Nginx configuration with EC2 DNS and dynamic location blocks."""
        try:
            # Read template
            if not self.nginx_template_path.exists():
                logger.warning(f"Nginx template not found at {self.nginx_template_path}")
                return False
                
            with open(self.nginx_template_path, "r") as f:
                template_content = f.read()
            
            # Get health service to check server health
            from ..health.service import health_service
            
            # Generate location blocks for enabled and healthy servers with transport support
            location_blocks = []
            for path, server_info in servers.items():
                proxy_pass_url = server_info.get("proxy_pass_url")
                if proxy_pass_url:
                    # Check if server is healthy (including auth-expired which is still reachable)
                    health_status = health_service.server_health_status.get(path, HealthStatus.UNKNOWN)
                    
                    # Include servers that are healthy or just have expired auth (server is up)
                    if HealthStatus.is_healthy(health_status):
                        # Generate transport-aware location blocks
                        transport_blocks = self._generate_transport_location_blocks(path, server_info)
                        location_blocks.extend(transport_blocks)
                        logger.debug(f"Added location blocks for healthy service: {path}")
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
            
            # Fetch EC2 public DNS
            ec2_public_dns = await self.get_ec2_public_dns()
            
            # Replace placeholders in template
            config_content = template_content.replace("{{LOCATION_BLOCKS}}", "\n".join(location_blocks))
            config_content = config_content.replace("{{EC2_PUBLIC_DNS}}", ec2_public_dns)
            
            # Write config file
            with open(settings.nginx_config_path, "w") as f:
                f.write(config_content)
                
            logger.info(f"Generated Nginx configuration with {len(location_blocks)} location blocks and EC2 DNS: {ec2_public_dns}")
            
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

            # Test the configuration first before reloading
            test_result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
            if test_result.returncode != 0:
                logger.error(f"Nginx configuration test failed: {test_result.stderr}")
                logger.info("Skipping Nginx reload due to configuration errors")
                return False

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


    def _generate_transport_location_blocks(self, path: str, server_info: Dict[str, Any]) -> list:
        """Generate nginx location blocks for different transport types."""
        blocks = []
        proxy_pass_url = server_info.get("proxy_pass_url", "")
        supported_transports = server_info.get("supported_transports", ["streamable-http"])
        
        # Use the proxy_pass_url exactly as specified in the JSON file
        # Users are responsible for including /mcp, /sse, or any other path in the URL
        proxy_url = proxy_pass_url
        
        # Determine transport type based on supported_transports
        if not supported_transports:
            # Default to streamable-http if no transports specified
            transport_type = "streamable-http"
            logger.info(f"Server {path}: No supported_transports specified, defaulting to streamable-http")
        elif "streamable-http" in supported_transports and "sse" in supported_transports:
            # If both are supported, prefer streamable-http
            transport_type = "streamable-http"
            logger.info(f"Server {path}: Both streamable-http and sse supported, preferring streamable-http")
        elif "sse" in supported_transports:
            # SSE only
            transport_type = "sse"
            logger.info(f"Server {path}: Only sse transport supported, using sse")
        elif "streamable-http" in supported_transports:
            # Streamable-http only
            transport_type = "streamable-http"
            logger.info(f"Server {path}: Only streamable-http transport supported, using streamable-http")
        else:
            # Default to streamable-http if unknown transport
            transport_type = "streamable-http"
            logger.info(f"Server {path}: Unknown transport types {supported_transports}, defaulting to streamable-http")
        
        # Create a single location block for this server
        # The proxy_pass URL is used exactly as provided in the server configuration
        logger.info(f"Server {path}: Using proxy_pass URL as configured: {proxy_url}")
        
        block = self._create_location_block(path, proxy_url, transport_type)
        blocks.append(block)
        
        return blocks


    def _create_location_block(self, path: str, proxy_pass_url: str, transport_type: str) -> str:
        """Create a single nginx location block with transport-specific configuration."""
        
        # Extract hostname from proxy_pass_url for external services
        parsed_url = urlparse(proxy_pass_url)
        upstream_host = parsed_url.netloc
        
        # Determine whether to use upstream hostname or preserve original host
        # For external services (https), use the upstream hostname
        # For internal services (http without dots in hostname), preserve original host
        if parsed_url.scheme == 'https' or '.' in upstream_host:
            # External service - use upstream hostname
            host_header = upstream_host
            logger.info(f"Using upstream hostname for Host header: {host_header}")
        else:
            # Internal service - preserve original host
            host_header = '$host'
            logger.info(f"Using original host for Host header: $host")
        
        # Common proxy settings
        common_settings = f"""
        # Authenticate request - pass entire request to auth server
        auth_request /validate;
        
        # Capture auth server response headers for forwarding
        auth_request_set $auth_user $upstream_http_x_user;
        auth_request_set $auth_username $upstream_http_x_username;
        auth_request_set $auth_client_id $upstream_http_x_client_id;
        auth_request_set $auth_scopes $upstream_http_x_scopes;
        auth_request_set $auth_method $upstream_http_x_auth_method;
        auth_request_set $auth_server_name $upstream_http_x_server_name;
        auth_request_set $auth_tool_name $upstream_http_x_tool_name;
        
        # Proxy to MCP server
        proxy_pass {proxy_pass_url};
        proxy_http_version 1.1;
        proxy_set_header Host {host_header};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add original URL for auth server scope validation
        proxy_set_header X-Original-URL $scheme://$host$request_uri;
        
        # Pass through the original authentication headers
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-Authorization $http_x_authorization;
        proxy_set_header X-User-Pool-Id $http_x_user_pool_id;
        proxy_set_header X-Client-Id $http_x_client_id;
        proxy_set_header X-Region $http_x_region;

        
        # Forward auth server response headers to backend
        proxy_set_header X-User $auth_user;
        proxy_set_header X-Username $auth_username;
        proxy_set_header X-Client-Id-Auth $auth_client_id;
        proxy_set_header X-Scopes $auth_scopes;
        proxy_set_header X-Auth-Method $auth_method;
        proxy_set_header X-Server-Name $auth_server_name;
        proxy_set_header X-Tool-Name $auth_tool_name;
        
        # Pass all original client headers
        proxy_pass_request_headers on;
        
        # Handle auth errors
        error_page 401 = @auth_error;
        error_page 403 = @forbidden_error;"""
        
        # Transport-specific settings
        if transport_type == "sse":
            transport_settings = """
        # Capture request body for auth validation using Lua
        rewrite_by_lua_file /etc/nginx/lua/capture_body.lua;
        
        # For SSE connections and WebSocket upgrades
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection $http_connection;
        proxy_set_header Upgrade $http_upgrade;
        chunked_transfer_encoding off;"""
        
        elif transport_type == "streamable-http":
            transport_settings = """
        # Capture request body for auth validation using Lua
        rewrite_by_lua_file /etc/nginx/lua/capture_body.lua;
        
        # HTTP transport configuration
        proxy_buffering off;
        proxy_set_header Connection "";"""
        
        else:  # direct
            transport_settings = """
        # Capture request body for auth validation using Lua
        rewrite_by_lua_file /etc/nginx/lua/capture_body.lua;
        
        # Generic transport configuration
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection $http_connection;
        proxy_set_header Upgrade $http_upgrade;
        chunked_transfer_encoding off;"""
        
        # Use the location path exactly as specified in the server configuration
        # Users have full control over the location path format (with or without trailing slash)
        location_path = path
        logger.info(f"Creating location block for {location_path} with {transport_type} transport")
        
        return f"""
    location {location_path} {{{transport_settings}{common_settings}
    }}"""


# Global nginx service instance
nginx_service = NginxConfigService() 
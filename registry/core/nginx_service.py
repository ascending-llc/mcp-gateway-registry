import logging
import asyncio
import httpx
from pathlib import Path
from typing import Dict, Any, Optional

from .config import settings

logger = logging.getLogger(__name__)


class NginxConfigService:
    """Service for generating Nginx configuration for registered servers."""
    
    def __init__(self):
        # Use the docker template file as the source template
        # Handle both container and local development paths
        if Path("/app/docker/nginx_rev_proxy.conf").exists():
            self.nginx_template_path = Path("/app/docker/nginx_rev_proxy.conf")
        else:
            # Fallback for local development
            self.nginx_template_path = Path("docker/nginx_rev_proxy.conf")
        
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
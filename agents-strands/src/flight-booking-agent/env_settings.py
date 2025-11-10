"""Environment settings for Flight Booking Agent"""

import os
from functools import lru_cache


class EnvSettings:
    def __init__(self):
        self.db_path: str = os.getenv("DB_PATH", "/app/data/bookings.db")
        self.aws_region: str = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.agent_name: str = os.getenv("AGENT_NAME", "flight-booking")
        self.agent_version: str = os.getenv("AGENT_VERSION", "1.0.0")
        
        # MCP Gateway Registry URL (TODO: replace later)
        self.mcp_registry_url: str = os.getenv("MCP_REGISTRY_URL", "http://localhost:7860")
        
        # Agent's public URL (AgentCore Runtime injects automatically)
        self.agent_url: str = os.getenv("AGENTCORE_RUNTIME_URL", "http://127.0.0.1:9000/")
        
        # Server configuration (fixed for A2A protocol)
        self.host: str = "0.0.0.0"
        self.port: int = 9000





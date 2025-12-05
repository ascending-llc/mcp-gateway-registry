"""
Check Current Configuration

Shows what provider and vectorizer are currently configured.
Useful for debugging configuration issues.

Usage:
    cd packages
    source .venv/bin/activate
    python -m db.example.check_config
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db import WeaviateClient, ProviderFactory, get_weaviate_client, init_weaviate
from db.core.config import ConnectionConfig


def main():
    """Check and display current configuration."""
    print("\n" + "=" * 70)
    print("Weaviate ORM Configuration Check")
    print("=" * 70)
    
    # Check environment variables
    print("\n📋 Environment Variables:")
    env_vars = [
        "WEAVIATE_HOST",
        "WEAVIATE_PORT",
        "WEAVIATE_API_KEY",
        "EMBEDDINGS_PROVIDER",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "OPENAI_API_KEY",
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if var in ["AWS_SECRET_ACCESS_KEY", "WEAVIATE_API_KEY", "OPENAI_API_KEY"] and value:
            # Mask sensitive values
            display = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        else:
            display = value or "(not set)"
        
        print(f"   {var:30s} = {display}")
    
    # Check provider configuration
    print("\n🔌 Provider Configuration:")
    try:
        provider = ProviderFactory.from_env()
        print(f"   Type: {provider.__class__.__name__}")
        print(f"   Vectorizer: {provider.get_vectorizer_name()}")
        print(f"   Model: {provider.get_model_name()}")
        
        # Check authentication method
        headers = provider.get_headers()
        if headers:
            print(f"   Authentication: Explicit credentials")
            print(f"   Headers: {list(headers.keys())}")
        else:
            print(f"   Authentication: IAM Role (instance profile)")
            print(f"   Headers: (empty - using AWS SDK default credential chain)")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Check connection configuration
    print("\n🌐 Connection Configuration:")
    try:
        config = ConnectionConfig.from_env()
        print(f"   Host: {config.host}")
        print(f"   Port: {config.port}")
        print(f"   API Key: {'(set)' if config.api_key else '(not set)'}")
        print(f"   Pool connections: {config.pool_connections}")
        print(f"   Pool maxsize: {config.pool_maxsize}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Try to connect
    print("\n🔗 Connection Test:")
    try:
        client = WeaviateClient()
        print(f"   ✅ Client created")
        
        if client.is_ready():
            print(f"   ✅ Client is connected")
        else:
            print(f"   ❌ Client not connected")
        
        if client.ping():
            print(f"   ✅ Server responding")
        else:
            print(f"   ❌ Server not responding")
        
        client.close()
        
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("Configuration Summary")
    print("=" * 70)
    
    provider_name = os.getenv("EMBEDDINGS_PROVIDER", "bedrock")
    aws_creds = os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    print(f"\n📊 Current Setup:")
    print(f"   Provider: {provider_name}")
    
    if provider_name == "bedrock":
        if aws_creds:
            print(f"   Auth Method: Explicit AWS credentials")
        else:
            print(f"   Auth Method: IAM Role / Instance Profile")
    elif provider_name == "openai":
        if openai_key:
            print(f"   Auth Method: OpenAI API Key")
        else:
            print(f"   ❌ Missing OPENAI_API_KEY")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    if provider_name == "bedrock" and not aws_creds:
        print(f"   ✅ Using IAM Role authentication")
        print(f"   This is recommended for EC2/ECS/EKS deployments")
        print(f"   Ensure your instance has appropriate IAM role attached")
    
    if provider_name == "openai" and not openai_key:
        print(f"   ❌ Set OPENAI_API_KEY environment variable")
    
    print(f"\n📝 When defining models:")
    print(f"   - Don't specify 'vectorizer' in Meta (uses provider default)")
    print(f"   - Or explicitly set: vectorizer = '{provider.get_vectorizer_name() if 'provider' in locals() else 'text2vec-xxx'}'")
    
    print("\n")


if __name__ == "__main__":
    main()



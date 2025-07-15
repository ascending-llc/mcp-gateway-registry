#!/usr/bin/env python3
"""
Standalone test client for testing currenttime server with both transports.
This validates the transport implementation before registry integration.
"""

import asyncio
import argparse
import sys
import traceback
import logging
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

# Configure debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable detailed HTTP logging
logging.getLogger("mcp").setLevel(logging.DEBUG)
logging.getLogger("anyio").setLevel(logging.DEBUG)


async def test_transport(server_url: str, transport: str):
    """Test specific transport type"""
    print(f"\n🔍 Testing {transport} transport")
    print(f"📡 Connecting to endpoint: {server_url}")
    
    try:
        if transport == "streamable-http":
            print(f"🔗 Using streamablehttp_client to connect to: {server_url}")
            async with streamablehttp_client(url=server_url) as (read, write, get_session_id):
                print(f"  ✓ StreamableHTTP connection established")
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    await session.initialize()
                    print(f"  ✓ Session initialized successfully")
                    
                    # List tools
                    print(f"  🔧 Calling session.list_tools()...")
                    tools_result = await session.list_tools()
                    tools = tools_result.tools
                    print(f"  ✓ Found {len(tools)} tools via streamable-http")
                    for tool in tools:
                        print(f"    - {tool.name}: {tool.description}")
                    
                    # Test tool call
                    if tools:
                        # Test with multiple timezones
                        test_timezones = ["UTC", "America/New_York"]  # Reduced for brevity
                        for tz in test_timezones:
                            try:
                                print(f"  🛠 Calling tool 'current_time_by_timezone' with tz_name='{tz}'...")
                                result = await session.call_tool("current_time_by_timezone", {"tz_name": tz})
                                time_str = result.content[0].text if result.content else "No result"
                                print(f"  ✓ Time in {tz}: {time_str}")
                            except Exception as tool_error:
                                print(f"  ✗ Failed to get time for {tz}: {tool_error}")
                    else:
                        print(f"  ⚠ No tools found to test")
                        
        elif transport == "sse":
            # For SSE, use the server_url as-is (it should include /sse)
            print(f"🔗 Using sse_client to connect to: {server_url}")
            async with sse_client(server_url) as (read, write):
                print(f"  ✓ SSE connection established")
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    await session.initialize()
                    print(f"  ✓ Session initialized successfully")
                    
                    # List tools
                    print(f"  🔧 Calling session.list_tools()...")
                    tools_result = await session.list_tools()
                    tools = tools_result.tools
                    print(f"  ✓ Found {len(tools)} tools via sse")
                    for tool in tools:
                        print(f"    - {tool.name}: {tool.description}")
                    
                    # Test tool call
                    if tools:
                        # Test with multiple timezones
                        test_timezones = ["UTC", "America/New_York"]  # Reduced for brevity
                        for tz in test_timezones:
                            try:
                                print(f"  🛠 Calling tool 'current_time_by_timezone' with tz_name='{tz}'...")
                                result = await session.call_tool("current_time_by_timezone", {"tz_name": tz})
                                time_str = result.content[0].text if result.content else "No result"
                                print(f"  ✓ Time in {tz}: {time_str}")
                            except Exception as tool_error:
                                print(f"  ✗ Failed to get time for {tz}: {tool_error}")
                    else:
                        print(f"  ⚠ No tools found to test")
                        
    except Exception as e:
        print(f"  ✗ {transport} transport failed: {e}")
        print(f"  📋 Full traceback:")
        traceback.print_exc()
        return False
    
    return True


async def test_server_health(base_url: str):
    """Test if the server is running and accessible"""
    import aiohttp
    
    print(f"🏥 Testing server health at {base_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test both potential endpoints
            base_url_clean = base_url.rstrip('/')
            for endpoint in ["/mcp", "/sse"]:
                url = f"{base_url_clean}{endpoint}"
                try:
                    async with session.get(url, timeout=5) as response:
                        print(f"  ✓ {endpoint} endpoint responding (status: {response.status})")
                except Exception as e:
                    print(f"  ℹ {endpoint} endpoint not accessible: {e}")
    except Exception as e:
        print(f"  ✗ Server health check failed: {e}")
        return False
    
    return True


async def main():
    parser = argparse.ArgumentParser(description="Test currenttime server transports")
    parser.add_argument("--base-url", default="http://localhost:8000", 
                       help="Base server URL (default: http://localhost:8000)")
    parser.add_argument("--transport", choices=["streamable-http", "sse", "both"], 
                       default="streamable-http", help="Which transport to test (default: streamable-http)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose HTTP logging (shows headers and payloads)")
    args = parser.parse_args()
    
    # Adjust logging based on verbosity
    if not args.verbose:
        # Reduce noise for normal operation
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("anyio").setLevel(logging.WARNING)
        logging.getLogger().setLevel(logging.INFO)
    else:
        print("🔍 Verbose mode enabled - showing all HTTP traffic")
        print("=" * 60)
    
    print("🧪 CurrentTime Server Transport Test")
    print("=" * 50)
    
    # Test server health first
    health_ok = await test_server_health(args.base_url)
    if not health_ok:
        print("\n❌ Server appears to be down or unreachable")
        print("💡 Make sure to start the server first:")
        print("   cd servers/currenttime")
        print("   uv run python server.py --transport streamable-http")
        print("   or for SSE:")
        print("   uv run python server.py --transport sse")
        return 1
    
    # Determine which transports to test
    transports_to_test = []
    base_url_clean = args.base_url.rstrip('/')
    if args.transport == "both":
        transports_to_test = [
            ("streamable-http", f"{base_url_clean}/mcp/"),
            ("sse", f"{base_url_clean}/sse")
        ]
    elif args.transport == "streamable-http":
        transports_to_test = [("streamable-http", f"{base_url_clean}/mcp/")]
    elif args.transport == "sse":
        transports_to_test = [("sse", f"{base_url_clean}/sse")]
    
    # Test transports
    results = {}
    for transport, url in transports_to_test:
        success = await test_transport(url, transport)
        results[transport] = success
    
    # Display results
    print("\n📊 Test Results:")
    print("-" * 30)
    all_passed = True
    for transport, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{transport:15}: {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        print(f"\n🎉 All tested transports working correctly!")
        return 0
    else:
        print(f"\n❌ Some transports failed")
        print("\n💡 Troubleshooting tips:")
        print("1. Make sure the server is running with the correct transport")
        print("2. Check the server logs for any errors")
        print("3. Verify the endpoint URLs are correct")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        sys.exit(1)
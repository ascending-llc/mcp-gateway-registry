"""
MCP Client Service

Handles connections to MCP servers and tool list retrieval.
Copied directly from main_old.py working implementation.
"""

import asyncio
import json
import logging
from typing import List, Dict, Optional

# MCP Client imports
from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


async def get_tools_from_server(base_url: str) -> List[dict] | None:
    """
    Connects to an MCP server via SSE, lists tools, and returns their details
    (name, description, schema).

    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).

    Returns:
        A list of tool detail dictionaries (keys: name, description, schema),
        or None if connection/retrieval fails.
    """
    # Determine scheme and construct the full /sse URL
    if not base_url:
        logger.error("MCP Check Error: Base URL is empty.")
        return None

    sse_url = base_url.rstrip('/') + "/sse"
    # Simple check for https, might need refinement for edge cases
    secure_prefix = "s" if sse_url.startswith("https://") else ""
    mcp_server_url = f"http{secure_prefix}://{sse_url[len(f'http{secure_prefix}://'):]}" # Ensure correct format for sse_client


    logger.info(f"Attempting to connect to MCP server at {mcp_server_url} to get tool list...")
    try:
        # Connect using the sse_client context manager directly
        async with sse_client(mcp_server_url) as (read, write):
             # Use the ClientSession context manager directly
            async with ClientSession(read, write, sampling_callback=None) as session:
                # Apply timeout to individual operations within the session
                await asyncio.wait_for(session.initialize(), timeout=10.0) # Timeout for initialize
                tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0) # Renamed variable

                # Extract tool details
                tool_details_list = []
                if tools_response and hasattr(tools_response, 'tools'):
                    for tool in tools_response.tools:
                        # Access attributes directly based on MCP documentation
                        tool_name = getattr(tool, 'name', 'Unknown Name') # Direct attribute access
                        tool_desc = getattr(tool, 'description', None) or getattr(tool, '__doc__', None)

                        # --- Parse Docstring into Sections --- START
                        parsed_desc = {
                            "main": "No description available.",
                            "args": None,
                            "returns": None,
                            "raises": None,
                        }
                        if tool_desc:
                            tool_desc = tool_desc.strip()
                            # Simple parsing logic (can be refined)
                            lines = tool_desc.split('\n')
                            main_desc_lines = []
                            current_section = "main"
                            section_content = []

                            for line in lines:
                                stripped_line = line.strip()
                                if stripped_line.startswith("Args:"):
                                    parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                                    current_section = "args"
                                    section_content = [stripped_line[len("Args:"):].strip()]
                                elif stripped_line.startswith("Returns:"):
                                    if current_section != "main": 
                                        parsed_desc[current_section] = "\n".join(section_content).strip()
                                    else: 
                                        parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                                    current_section = "returns"
                                    section_content = [stripped_line[len("Returns:"):].strip()]
                                elif stripped_line.startswith("Raises:"):
                                    if current_section != "main": 
                                        parsed_desc[current_section] = "\n".join(section_content).strip()
                                    else: 
                                        parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                                    current_section = "raises"
                                    section_content = [stripped_line[len("Raises:"):].strip()]
                                elif current_section == "main":
                                    main_desc_lines.append(line.strip()) # Keep leading whitespace for main desc if intended
                                else:
                                    section_content.append(line.strip())

                            # Add the last collected section
                            if current_section != "main":
                                parsed_desc[current_section] = "\n".join(section_content).strip()
                            elif not parsed_desc["main"] and main_desc_lines: # Handle case where entire docstring was just main description
                                parsed_desc["main"] = "\n".join(main_desc_lines).strip()

                            # Ensure main description has content if others were parsed but main was empty
                            if not parsed_desc["main"] and (parsed_desc["args"] or parsed_desc["returns"] or parsed_desc["raises"]):
                                parsed_desc["main"] = "(No primary description provided)"

                        else:
                            parsed_desc["main"] = "No description available."
                        # --- Parse Docstring into Sections --- END

                        tool_schema = getattr(tool, 'inputSchema', {}) # Use inputSchema attribute

                        tool_details_list.append({
                            "name": tool_name,
                            "parsed_description": parsed_desc, # Store parsed sections
                            "schema": tool_schema
                        })

                logger.info(f"Successfully retrieved details for {len(tool_details_list)} tools from {mcp_server_url}.")
                return tool_details_list # Return the list of details
    except asyncio.TimeoutError:
        logger.error(f"MCP Check Error: Timeout during session operation with {mcp_server_url}.")
        return None
    except ConnectionRefusedError:
         logger.error(f"MCP Check Error: Connection refused by {mcp_server_url}.")
         return None
    except Exception as e:
        logger.error(f"MCP Check Error: Failed to get tool list from {mcp_server_url}: {type(e).__name__} - {e}")
        return None


class MCPClientService:
    """Service wrapper for the MCP client function to maintain compatibility."""
    
    async def get_tools_from_server(self, base_url: str) -> Optional[List[Dict]]:
        """Wrapper method to maintain compatibility with existing code."""
        return await get_tools_from_server(base_url)


# Global MCP client service instance  
mcp_client_service = MCPClientService() 
"""
This server provides tools to interact with the MCP Gateway Registry API.
"""

import os
import httpx # Use httpx for async requests
import argparse
import asyncio # Added for locking
import logging
import json
import websockets # For WebSocket connections
from pathlib import Path # Added Path
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, Optional, ClassVar, List
from dotenv import load_dotenv
import os
from sentence_transformers import SentenceTransformer # Added
import numpy as np # Added
from sklearn.metrics.pairwise import cosine_similarity # Added
import faiss # Added

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file

# Get Registry URL from environment variable (keep this one)
REGISTRY_BASE_URL = os.environ.get("REGISTRY_BASE_URL", "http://localhost:7860") # Default to localhost

if not REGISTRY_BASE_URL:
    raise ValueError("REGISTRY_BASE_URL environment variable is not set.")


# --- FAISS and Sentence Transformer Integration for mcpgw --- START
_faiss_data_lock = asyncio.Lock()
_embedding_model_mcpgw: Optional[SentenceTransformer] = None
_faiss_index_mcpgw: Optional[faiss.Index] = None
_faiss_metadata_mcpgw: Optional[Dict[str, Any]] = None # This will store the content of service_index_metadata.json
_last_faiss_index_mtime: Optional[float] = None
_last_faiss_metadata_mtime: Optional[float] = None

# Determine base path for mcpgw server to find registry's server data
# When running in Docker, server.py is at /app/server.py and registry files are at /app/registry/servers/
_registry_server_data_path = Path(__file__).resolve().parent / "registry" / "servers"
FAISS_INDEX_PATH_MCPGW = _registry_server_data_path / "service_index.faiss"
FAISS_METADATA_PATH_MCPGW = _registry_server_data_path / "service_index_metadata.json"
EMBEDDING_DIMENSION_MCPGW = 384 # Should match the one used in main registry

# Get configuration from environment variables
EMBEDDINGS_MODEL_NAME = os.environ.get('EMBEDDINGS_MODEL_NAME', 'all-MiniLM-L6-v2')
EMBEDDINGS_MODEL_DIR = _registry_server_data_path.parent / "models" / EMBEDDINGS_MODEL_NAME

async def load_faiss_data_for_mcpgw():
    """Loads the FAISS index, metadata, and embedding model for the mcpgw server.
       Reloads data if underlying files have changed since last load.
    """
    global _embedding_model_mcpgw, _faiss_index_mcpgw, _faiss_metadata_mcpgw
    global _last_faiss_index_mtime, _last_faiss_metadata_mtime
    
    async with _faiss_data_lock:
        # Load embedding model if not already loaded (model doesn't change on disk typically)
        if _embedding_model_mcpgw is None:
            try:
                model_cache_path = _registry_server_data_path.parent / ".cache"
                model_cache_path.mkdir(parents=True, exist_ok=True)
                
                # Set SENTENCE_TRANSFORMERS_HOME to use the defined cache path
                original_st_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
                os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(model_cache_path)
                
                # Check if the model path exists and is not empty
                model_path = Path(EMBEDDINGS_MODEL_DIR)
                model_exists = model_path.exists() and any(model_path.iterdir()) if model_path.exists() else False
                
                if model_exists:
                    logger.info(f"MCPGW: Loading SentenceTransformer model from local path: {EMBEDDINGS_MODEL_DIR}")
                    _embedding_model_mcpgw = await asyncio.to_thread(SentenceTransformer, str(EMBEDDINGS_MODEL_DIR))
                else:
                    logger.info(f"MCPGW: Local model not found at {EMBEDDINGS_MODEL_DIR}, downloading from Hugging Face")
                    _embedding_model_mcpgw = await asyncio.to_thread(SentenceTransformer, str(EMBEDDINGS_MODEL_NAME))
                
                # Restore original environment variable if it was set
                if original_st_home:
                    os.environ['SENTENCE_TRANSFORMERS_HOME'] = original_st_home
                else:
                    del os.environ['SENTENCE_TRANSFORMERS_HOME'] # Remove if not originally set
                    
                logger.info("MCPGW: SentenceTransformer model loaded successfully.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load SentenceTransformer model: {e}", exc_info=True)
                return # Cannot proceed without the model for subsequent logic

        # Check FAISS index file
        index_file_changed = False
        if FAISS_INDEX_PATH_MCPGW.exists():
            try:
                current_index_mtime = await asyncio.to_thread(os.path.getmtime, FAISS_INDEX_PATH_MCPGW)
                if _faiss_index_mcpgw is None or _last_faiss_index_mtime is None or current_index_mtime > _last_faiss_index_mtime:
                    logger.info(f"MCPGW: FAISS index file {FAISS_INDEX_PATH_MCPGW} has changed or not loaded. Reloading...")
                    _faiss_index_mcpgw = await asyncio.to_thread(faiss.read_index, str(FAISS_INDEX_PATH_MCPGW))
                    _last_faiss_index_mtime = current_index_mtime
                    index_file_changed = True # Mark that it was reloaded
                    logger.info(f"MCPGW: FAISS index loaded. Total vectors: {_faiss_index_mcpgw.ntotal}")
                    if _faiss_index_mcpgw.d != EMBEDDING_DIMENSION_MCPGW:
                        logger.warning(f"MCPGW: Loaded FAISS index dimension ({_faiss_index_mcpgw.d}) differs from expected ({EMBEDDING_DIMENSION_MCPGW}). Search might be compromised.")
                else:
                    logger.debug("MCPGW: FAISS index file unchanged since last load.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load or check FAISS index: {e}", exc_info=True)
                _faiss_index_mcpgw = None # Ensure it's None on error
        else:
            logger.warning(f"MCPGW: FAISS index file {FAISS_INDEX_PATH_MCPGW} does not exist.")
            _faiss_index_mcpgw = None
            _last_faiss_index_mtime = None

        # Check FAISS metadata file
        metadata_file_changed = False
        if FAISS_METADATA_PATH_MCPGW.exists():
            try:
                current_metadata_mtime = await asyncio.to_thread(os.path.getmtime, FAISS_METADATA_PATH_MCPGW)
                if _faiss_metadata_mcpgw is None or _last_faiss_metadata_mtime is None or current_metadata_mtime > _last_faiss_metadata_mtime or index_file_changed:
                    logger.info(f"MCPGW: FAISS metadata file {FAISS_METADATA_PATH_MCPGW} has changed, not loaded, or index changed. Reloading...")
                    with open(FAISS_METADATA_PATH_MCPGW, "r") as f:
                        content = await asyncio.to_thread(f.read)
                        _faiss_metadata_mcpgw = await asyncio.to_thread(json.loads, content)
                    _last_faiss_metadata_mtime = current_metadata_mtime
                    metadata_file_changed = True
                    logger.info(f"MCPGW: FAISS metadata loaded. Paths: {len(_faiss_metadata_mcpgw.get('metadata', {})) if _faiss_metadata_mcpgw else 'N/A'}")
                else:
                    logger.debug("MCPGW: FAISS metadata file unchanged since last load.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load or check FAISS metadata: {e}", exc_info=True)
                _faiss_metadata_mcpgw = None # Ensure it's None on error
        else:
            logger.warning(f"MCPGW: FAISS metadata file {FAISS_METADATA_PATH_MCPGW} does not exist.")
            _faiss_metadata_mcpgw = None
            _last_faiss_metadata_mtime = None

# Call it once at startup, but allow lazy loading if it fails initially
# This direct call might be problematic if server.py is imported elsewhere before app runs.
# A better approach would be a startup event if FastMCP supports it.
# For now, it will attempt to load on first tool call if still None.
# asyncio.create_task(load_faiss_data_for_mcpgw()) # Consider FastMCP startup hook

# --- FAISS and Sentence Transformer Integration for mcpgw --- END


class Constants(BaseModel):
    # Using ClassVar to define class-level constants
    DESCRIPTION: ClassVar[str] = "MCP Gateway Registry Interaction Server (mcpgw)"
    DEFAULT_MCP_TRANSPORT: ClassVar[str] = "sse"
    DEFAULT_MCP_SEVER_LISTEN_PORT: ClassVar[str] = "8003" # Default to a different port
    REQUEST_TIMEOUT: ClassVar[float] = 15.0 # Timeout for HTTP requests

    # Disable instance creation - optional but recommended for constants
    class Config:
        frozen = True  # Make instances immutable


def parse_arguments():
    """Parse command line arguments with defaults matching environment variables."""
    parser = argparse.ArgumentParser(description=Constants.DESCRIPTION)

    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get(
            "MCP_SERVER_LISTEN_PORT", Constants.DEFAULT_MCP_SEVER_LISTEN_PORT
        ),
        help=f"Port for the MCP server to listen on (default: {Constants.DEFAULT_MCP_SEVER_LISTEN_PORT})",
    )

    parser.add_argument(
        "--transport",
        type=str,
        default=os.environ.get("MCP_TRANSPORT", Constants.DEFAULT_MCP_TRANSPORT),
        help=f"Transport type for the MCP server (default: {Constants.DEFAULT_MCP_TRANSPORT})",
    )

    return parser.parse_args()


# Parse arguments at module level to make them available
args = parse_arguments()

# Initialize FastMCP server
mcp = FastMCP("MCPGateway", host="0.0.0.0", port=int(args.port))
mcp.settings.mount_path = "/mcpgw"


# --- Helper function for making requests to the registry ---
async def _call_registry_api(method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
    """
    Helper function to make async requests to the registry API.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        **kwargs: Additional arguments to pass to the HTTP request
        
    Returns:
        Dict[str, Any]: JSON response from the API
    """
    url = f"{REGISTRY_BASE_URL.rstrip('/')}{endpoint}"

    # Use a single client instance for potential connection pooling benefits
    async with httpx.AsyncClient(timeout=Constants.REQUEST_TIMEOUT) as client:
        try:
            logger.info(f"Calling Registry API: {method} {url}") # Log the actual call
            response = await client.request(method, url, **kwargs)
            response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)

            # Handle cases where response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return {"status": "success", "message": "Operation successful, no content returned."}
            return response.json()

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors
            error_detail = "No specific error detail provided."
            try:
                error_detail = e.response.json().get("detail", error_detail)
            except Exception as json_error:
                # Log that we couldn't get detailed error from JSON, but continue with existing error info
                logger.debug(f"MCPGW: Could not extract detailed error from response: {json_error}")
            raise Exception(f"Registry API Error ({e.response.status_code}): {error_detail} for {method} {url}") from e
        except httpx.RequestError as e:
            # Network or connection error during the API call
            raise Exception(f"Registry API Request Error: Failed to connect or communicate with {url}. Details: {e}") from e
        except Exception as e: # Catch other potential errors during API call
             raise Exception(f"An unexpected error occurred while calling the Registry API at {url}: {e}") from e


# --- MCP Tools ---

@mcp.tool()
async def toggle_service(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'."),
) -> Dict[str, Any]:
    """
    Toggles the enabled/disabled state of a registered MCP server in the gateway.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.

    Returns:
        Dict[str, Any]: Response from the registry API indicating success or failure.

    Raises:
        Exception: If the API call fails.
    """
    endpoint = f"/toggle/{service_path.lstrip('/')}" # Ensure path doesn't have double slash
        
    return await _call_registry_api("POST", endpoint)


@mcp.tool()
async def register_service(
    server_name: str = Field(..., description="Display name for the server."),
    path: str = Field(..., description="Unique URL path prefix for the server (e.g., '/my-service'). Must start with '/'."),
    proxy_pass_url: str = Field(..., description="The internal URL where the actual MCP server is running (e.g., 'http://localhost:8001')."),
    description: Optional[str] = Field("", description="Description of the server."),
    tags: Optional[List[str]] = Field(None, description="Optional list of tags for categorization."),
    num_tools: Optional[int] = Field(0, description="Number of tools provided by the server."),
    num_stars: Optional[int] = Field(0, description="Number of stars/rating for the server."),
    is_python: Optional[bool] = Field(False, description="Whether the server is implemented in Python."),
    license: Optional[str] = Field("N/A", description="License information for the server."),
) -> Dict[str, Any]:
    """
    Registers a new MCP server with the gateway.
    
    Args:
        server_name: Display name for the server.
        path: Unique URL path prefix for the server (e.g., '/my-service'). Must start with '/'.
        proxy_pass_url: The internal URL where the actual MCP server is running (e.g., 'http://localhost:8001').
        description: Description of the server.
        tags: Optional list of tags for categorization.
        num_tools: Number of tools provided by the server.
        num_stars: Number of stars/rating for the server.
        is_python: Whether the server is implemented in Python.
        license: License information for the server.
        
    Returns:
        Dict[str, Any]: Response from the registry API, likely including the registered server details.
        
    Raises:
        Exception: If the API call fails.
    """
    endpoint = "/register"
    
    # Convert tags list to comma-separated string if it's a list
    tags_str = ",".join(tags) if isinstance(tags, list) and tags is not None else tags
    
    # Create form data to send to the API
    form_data = {
        "name": server_name,  # Use 'name' as expected by the registry API
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "description": description if description is not None else "",
        "tags": tags_str if tags_str is not None else "",
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license": license  # The registry API uses alias="license" for license_str
    }
    # Remove None values
    form_data = {k: v for k, v in form_data.items() if v is not None}
    
    # Send as form data instead of JSON
    return await _call_registry_api("POST", endpoint, data=form_data)

@mcp.tool()
async def get_service_tools(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'. Use '/all' to get tools from all registered servers."),
) -> Dict[str, Any]:
    """
    Lists the tools provided by a specific registered MCP server.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.
                      Use '/all' to get tools from all registered servers.

    Returns:
        Dict[str, Any]: A list of tools exposed by the specified server.

    Raises:
        Exception: If the API call fails or the server cannot be reached.
    """
    endpoint = f"/api/tools/{service_path.lstrip('/')}"
        
    return await _call_registry_api("GET", endpoint)

@mcp.tool()
async def refresh_service(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'."),
) -> Dict[str, Any]:
    """
    Triggers a refresh of the tool list for a specific registered MCP server.
    The registry will re-connect to the target server to get its latest tools.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.

    Returns:
        Dict[str, Any]: Response from the registry API indicating the result of the refresh attempt.

    Raises:
        Exception: If the API call fails.
    """
    endpoint = f"/api/refresh/{service_path.lstrip('/')}"
        
    return await _call_registry_api("POST", endpoint)


@mcp.tool()
async def get_server_details(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'. Use '/all' to get details for all registered servers."),
) -> Dict[str, Any]:
    """
    Retrieves detailed information about a registered MCP server.
    
    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.
                      Use '/all' to get details for all registered servers.
        
    Returns:
        Dict[str, Any]: Detailed information about the specified server or all servers if '/all' is specified.
        
    Raises:
        Exception: If the API call fails or the server is not registered.
    """
    endpoint = f"/api/server_details/{service_path.lstrip('/')}"
        
    return await _call_registry_api("GET", endpoint)


@mcp.tool()
async def healthcheck() -> Dict[str, Any]:
    """
    Retrieves health status information from all registered MCP servers via the registry's WebSocket endpoint.
    
    Returns:
        Dict[str, Any]: Health status information for all registered servers, including:
            - status: 'healthy' or 'disabled'
            - last_checked_iso: ISO timestamp of when the server was last checked
            - num_tools: Number of tools provided by the server
            
    Raises:
        Exception: If the WebSocket connection fails or the data cannot be retrieved.
    """
    try:
        # Connect to the WebSocket endpoint
        registry_ws_url = f"ws://localhost:7860/ws/health_status"
        logger.info(f"Connecting to WebSocket endpoint: {registry_ws_url}")
        
        async with websockets.connect(registry_ws_url) as websocket:
            # WebSocket connection established, wait for the health status data
            logger.info("WebSocket connection established, waiting for health status data...")
            response = await websocket.recv()
            
            # Parse the JSON response
            health_data = json.loads(response)
            logger.info(f"Received health status data for {len(health_data)} servers")
            
            return health_data
            
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error: {e}")
        raise Exception(f"Failed to connect to health status WebSocket: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise Exception(f"Failed to parse health status data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving health status: {e}")
        raise Exception(f"Unexpected error retrieving health status: {e}")


@mcp.tool()
async def intelligent_tool_finder(
    natural_language_query: str = Field(..., description="Your query in natural language describing the task you want to perform."),
    top_k_services: int = Field(3, description="Number of top services to consider from initial FAISS search."),
    top_n_tools: int = Field(1, description="Number of best matching tools to return.")
) -> List[Dict[str, Any]]:
    """
    Finds the most relevant MCP tool(s) across all registered and enabled services
    based on a natural language query, using semantic search on the registry's FAISS index.

    Args:
        natural_language_query: The user's natural language query.
        top_k_services: How many top-matching services to analyze for tools.
        top_n_tools: How many best tools to return from the combined list.

    Returns:
        A list of dictionaries, each describing a recommended tool, its parent service, and similarity.
    """
    global _embedding_model_mcpgw, _faiss_index_mcpgw, _faiss_metadata_mcpgw

    # Ensure FAISS data and model are loaded
    if _embedding_model_mcpgw is None or _faiss_index_mcpgw is None or _faiss_metadata_mcpgw is None:
        logger.info("MCPGW: FAISS data or model not yet loaded. Attempting to load now for intelligent_tool_finder...")
        await load_faiss_data_for_mcpgw()

    if _embedding_model_mcpgw is None:
        raise Exception("MCPGW: Sentence embedding model is not available. Cannot perform intelligent search.")
    if _faiss_index_mcpgw is None:
        raise Exception("MCPGW: FAISS index is not available. Cannot perform intelligent search.")
    if _faiss_metadata_mcpgw is None or "metadata" not in _faiss_metadata_mcpgw:
        raise Exception("MCPGW: FAISS metadata is not available or in unexpected format. Cannot perform intelligent search.")

    registry_faiss_metadata = _faiss_metadata_mcpgw["metadata"] # This is {service_path: {id, text, full_server_info}}

    # 1. Embed the natural language query
    try:
        query_embedding = await asyncio.to_thread(_embedding_model_mcpgw.encode, [natural_language_query])
        query_embedding_np = np.array(query_embedding, dtype=np.float32)
    except Exception as e:
        logger.error(f"MCPGW: Error encoding natural language query: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error encoding query: {e}")

    # 2. Search FAISS for top_k_services
    # The FAISS index in registry/main.py stores SERVICE embeddings.
    try:
        logger.info(f"MCPGW: Searching FAISS index for top {top_k_services} services matching query.")
        distances, faiss_ids = await asyncio.to_thread(_faiss_index_mcpgw.search, query_embedding_np, top_k_services)
    except Exception as e:
        logger.error(f"MCPGW: Error searching FAISS index: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error searching FAISS index: {e}")

    candidate_tools = []
    
    # Create a reverse map from FAISS internal ID to service_path for quick lookup
    id_to_service_path_map = {}
    for Svc_path, meta_item in registry_faiss_metadata.items():
        if "id" in meta_item:
            id_to_service_path_map[meta_item["id"]] = Svc_path
        else:
            logger.warning(f"MCPGW: Metadata for service {Svc_path} missing 'id' field. Skipping.")


    # 3. Filter and Collect Tools from top services
    logger.info(f"MCPGW: Processing {len(faiss_ids[0])} services from FAISS search results.")
    for i in range(len(faiss_ids[0])):
        faiss_id = faiss_ids[0][i]
        if faiss_id == -1: # FAISS uses -1 for no more results or if k > ntotal
            continue

        service_path = id_to_service_path_map.get(faiss_id)
        if not service_path:
            logger.warning(f"MCPGW: Could not find service_path for FAISS ID {faiss_id}. Skipping.")
            continue
            
        service_metadata = registry_faiss_metadata.get(service_path)
        if not service_metadata or "full_server_info" not in service_metadata:
            logger.warning(f"MCPGW: Metadata or full_server_info not found for service path {service_path}. Skipping.")
            continue
            
        full_server_info = service_metadata["full_server_info"]

        if not full_server_info.get("is_enabled", False):
            logger.info(f"MCPGW: Service {service_path} is disabled. Skipping its tools.")
            continue

        service_name = full_server_info.get("server_name", "Unknown Service")
        tool_list = full_server_info.get("tool_list", [])

        for tool_info in tool_list:
            tool_name = tool_info.get("name", "Unknown Tool")
            parsed_desc = tool_info.get("parsed_description", {})
            main_desc = parsed_desc.get("main", "No description.")
            
            # Create descriptive text for this specific tool
            tool_text_for_embedding = f"Service: {service_name}. Tool: {tool_name}. Description: {main_desc}"
            
            candidate_tools.append({
                "text_for_embedding": tool_text_for_embedding,
                "tool_name": tool_name,
                "tool_parsed_description": parsed_desc,
                "tool_schema": tool_info.get("schema", {}),
                "service_path": service_path,
                "service_name": service_name,
            })

    if not candidate_tools:
        logger.info("MCPGW: No enabled tools found in the top services from FAISS search.")
        return []

    # 4. Embed all candidate tool descriptions
    logger.info(f"MCPGW: Embedding {len(candidate_tools)} candidate tools for secondary ranking.")
    try:
        tool_texts = [tool["text_for_embedding"] for tool in candidate_tools]
        tool_embeddings = await asyncio.to_thread(_embedding_model_mcpgw.encode, tool_texts)
        tool_embeddings_np = np.array(tool_embeddings, dtype=np.float32)
    except Exception as e:
        logger.error(f"MCPGW: Error encoding tool descriptions: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error encoding tool descriptions: {e}")

    # 5. Calculate cosine similarity between query and each tool embedding
    similarities = cosine_similarity(query_embedding_np, tool_embeddings_np)[0] # Get the first row (query vs all tools)

    # 6. Add similarity score to each tool and sort
    ranked_tools = []
    for i, tool_data in enumerate(candidate_tools):
        ranked_tools.append({
            **tool_data,
            "overall_similarity_score": float(similarities[i])
        })
    
    ranked_tools.sort(key=lambda x: x["overall_similarity_score"], reverse=True)

    # 7. Select top N tools
    final_results = ranked_tools[:top_n_tools]
    logger.info(f"MCPGW: Top {len(final_results)} tools found: {json.dumps(final_results, indent=2)}")
    
    # Remove the temporary 'text_for_embedding' field from results
    for res in final_results:
        del res["text_for_embedding"]
        
    return final_results


# --- Main Execution ---

def main():
    # Run the server with the specified transport from command line args
    mcp.run(transport=args.transport)
    logger.info(f"Server is running on port {args.port} with transport {args.transport}")


if __name__ == "__main__":
    main()
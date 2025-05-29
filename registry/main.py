import os
import json
import secrets
import asyncio
import subprocess
# argparse removed as we're using environment variables instead
from contextlib import asynccontextmanager
from pathlib import Path  # Import Path
from typing import Annotated, List, Set
from datetime import datetime, timezone

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# Get configuration from environment variables
EMBEDDINGS_MODEL_NAME = os.environ.get('EMBEDDINGS_MODEL_NAME', 'all-MiniLM-L6-v2')
EMBEDDINGS_MODEL_DIMENSIONS = int(os.environ.get('EMBEDDINGS_MODEL_DIMENSIONS', '384'))

from fastapi import (
    FastAPI,
    Request,
    Depends,
    HTTPException,
    Form,
    status,
    Cookie,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
import logging

# --- MCP Client Imports --- START
from mcp import ClientSession
from mcp.client.sse import sse_client
# --- MCP Client Imports --- END

# --- Define paths based on container structure --- START
CONTAINER_APP_DIR = Path("/app")
CONTAINER_REGISTRY_DIR = CONTAINER_APP_DIR / "registry"
CONTAINER_LOG_DIR = CONTAINER_APP_DIR / "logs"
EMBEDDINGS_MODEL_DIR = CONTAINER_REGISTRY_DIR / "models" / EMBEDDINGS_MODEL_NAME
# --- Define paths based on container structure --- END

# Determine the base directory of this script (registry folder)
# BASE_DIR = Path(__file__).resolve().parent # Less relevant inside container

# --- Load .env if it exists in the expected location relative to the app --- START
# Assumes .env might be mounted at /app/.env or similar
# DOTENV_PATH = BASE_DIR / ".env"
DOTENV_PATH = CONTAINER_REGISTRY_DIR / ".env" # Use container path
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH)
    print(f"Loaded environment variables from {DOTENV_PATH}")
else:
    print(f"Warning: .env file not found at {DOTENV_PATH}")
# --- Load .env if it exists in the expected location relative to the app --- END

# --- Configuration & State (Paths relative to container structure) ---
# Assumes nginx config might be placed alongside registry code
# NGINX_CONFIG_PATH = (
#     CONTAINER_REGISTRY_DIR / "nginx_mcp_revproxy.conf"
# )
NGINX_CONFIG_PATH = Path("/etc/nginx/conf.d/nginx_rev_proxy.conf") # Target the actual Nginx config file
# Use the mounted volume path for server definitions
SERVERS_DIR = CONTAINER_REGISTRY_DIR / "servers"
STATIC_DIR = CONTAINER_REGISTRY_DIR / "static"
TEMPLATES_DIR = CONTAINER_REGISTRY_DIR / "templates"
# NGINX_TEMPLATE_PATH = CONTAINER_REGISTRY_DIR / "nginx_template.conf"
# Use the mounted volume path for state file, keep it with servers
STATE_FILE_PATH = SERVERS_DIR / "server_state.json"
# Define log file path
# LOG_FILE_PATH = BASE_DIR / "registry.log"
LOG_FILE_PATH = CONTAINER_LOG_DIR / "registry.log"

# --- FAISS Vector DB Configuration --- START
FAISS_INDEX_PATH = SERVERS_DIR / "service_index.faiss"
FAISS_METADATA_PATH = SERVERS_DIR / "service_index_metadata.json"
EMBEDDING_MODEL_DIMENSION = EMBEDDINGS_MODEL_DIMENSIONS  # Use env var, default is 384 for all-MiniLM-L6-v2
# EMBEDDINGS_MODEL_NAME is already defined above
EMBEDDINGS_MODEL_PATH = EMBEDDINGS_MODEL_DIR  # Path derived from model name
embedding_model = None # Will be loaded in lifespan
faiss_index = None     # Will be loaded/created in lifespan
# Stores: { service_path: {"id": faiss_internal_id, "text_for_embedding": "...", "full_server_info": { ... }} }
# faiss_internal_id is the ID used with faiss_index.add_with_ids()
faiss_metadata_store = {}
next_faiss_id_counter = 0
# --- FAISS Vector DB Configuration --- END

# --- REMOVE Logging Setup from here --- START
# # Ensure log directory exists
# CONTAINER_LOG_DIR.mkdir(parents=True, exist_ok=True)
#
# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler(LOG_FILE_PATH), # Log to file in /app/logs
#         logging.StreamHandler() # Log to console (stdout/stderr)
#     ]
# )
#
# logger = logging.getLogger(__name__) # Get a logger instance
# logger.info("Logging configured. Application starting...")
# --- REMOVE Logging Setup from here --- END

# --- Define logger at module level (unconfigured initially) --- START
# Configure logging with process ID, filename, line number, and millisecond precision
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
# --- Define logger at module level (unconfigured initially) --- END

# In-memory state store
REGISTERED_SERVERS = {}
MOCK_SERVICE_STATE = {}
SERVER_HEALTH_STATUS = {} # Added for health check status: path -> 'healthy' | 'unhealthy' | 'checking' | 'error: <msg>'
HEALTH_CHECK_INTERVAL_SECONDS = 300 # Check every 5 minutes (restored)
HEALTH_CHECK_TIMEOUT_SECONDS = 10  # Timeout for each curl check (Increased to 10)
SERVER_LAST_CHECK_TIME = {} # path -> datetime of last check attempt (UTC)

# --- WebSocket Connection Management ---
active_connections: Set[WebSocket] = set()

# --- FAISS Helper Functions --- START

def _get_text_for_embedding(server_info: dict) -> str:
    """Prepares a consistent text string from server info for embedding."""
    name = server_info.get("server_name", "")
    description = server_info.get("description", "")
    tags = server_info.get("tags", [])
    tag_string = ", ".join(tags)
    return f"Name: {name}\\nDescription: {description}\\nTags: {tag_string}"

def load_faiss_data():
    global faiss_index, faiss_metadata_store, embedding_model, next_faiss_id_counter, CONTAINER_REGISTRY_DIR, SERVERS_DIR
    logger.info("Loading FAISS data and embedding model...")

    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    

    try:
        model_cache_path = CONTAINER_REGISTRY_DIR / ".cache"
        model_cache_path.mkdir(parents=True, exist_ok=True)
        
        # Set SENTENCE_TRANSFORMERS_HOME to use the defined cache path
        original_st_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
        os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(model_cache_path)
        
        # Check if the model path exists and is not empty
        model_path = Path(EMBEDDINGS_MODEL_PATH)
        model_exists = model_path.exists() and any(model_path.iterdir()) if model_path.exists() else False
        
        if model_exists:
            logger.info(f"Loading SentenceTransformer model from local path: {EMBEDDINGS_MODEL_PATH}")
            embedding_model = SentenceTransformer(str(EMBEDDINGS_MODEL_PATH))
        else:
            logger.info(f"Local model not found at {EMBEDDINGS_MODEL_PATH}, downloading from Hugging Face")
            embedding_model = SentenceTransformer(str(EMBEDDINGS_MODEL_NAME))
        
        # Restore original environment variable if it was set
        if original_st_home:
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = original_st_home
        else:
            del os.environ['SENTENCE_TRANSFORMERS_HOME'] # Remove if not originally set
            
        logger.info("SentenceTransformer model loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
        embedding_model = None 

    if FAISS_INDEX_PATH.exists() and FAISS_METADATA_PATH.exists():
        try:
            logger.info(f"Loading FAISS index from {FAISS_INDEX_PATH}")
            faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
            logger.info(f"Loading FAISS metadata from {FAISS_METADATA_PATH}")
            with open(FAISS_METADATA_PATH, "r") as f:
                loaded_metadata = json.load(f)
                faiss_metadata_store = loaded_metadata.get("metadata", {})
                next_faiss_id_counter = loaded_metadata.get("next_id", 0)
            logger.info(f"FAISS data loaded. Index size: {faiss_index.ntotal if faiss_index else 0}. Next ID: {next_faiss_id_counter}")
            if faiss_index and faiss_index.d != EMBEDDING_MODEL_DIMENSION:
                logger.warning(f"Loaded FAISS index dimension ({faiss_index.d}) differs from expected ({EMBEDDING_MODEL_DIMENSION}). Re-initializing.")
                faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(EMBEDDING_MODEL_DIMENSION))
                faiss_metadata_store = {}
                next_faiss_id_counter = 0
        except Exception as e:
            logger.error(f"Error loading FAISS data: {e}. Re-initializing.", exc_info=True)
            faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(EMBEDDING_MODEL_DIMENSION))
            faiss_metadata_store = {}
            next_faiss_id_counter = 0
    else:
        logger.info("FAISS index or metadata not found. Initializing new.")
        faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(EMBEDDING_MODEL_DIMENSION))
        faiss_metadata_store = {}
        next_faiss_id_counter = 0

def save_faiss_data():
    global faiss_index, faiss_metadata_store, next_faiss_id_counter
    if faiss_index is None:
        logger.error("FAISS index is not initialized. Cannot save.")
        return
    try:
        SERVERS_DIR.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        logger.info(f"Saving FAISS index to {FAISS_INDEX_PATH} (Size: {faiss_index.ntotal})")
        faiss.write_index(faiss_index, str(FAISS_INDEX_PATH))
        logger.info(f"Saving FAISS metadata to {FAISS_METADATA_PATH}")
        with open(FAISS_METADATA_PATH, "w") as f:
            json.dump({"metadata": faiss_metadata_store, "next_id": next_faiss_id_counter}, f, indent=2)
        logger.info("FAISS data saved successfully.")
    except Exception as e:
        logger.error(f"Error saving FAISS data: {e}", exc_info=True)

async def add_or_update_service_in_faiss(service_path: str, server_info: dict):
    global faiss_index, faiss_metadata_store, embedding_model, next_faiss_id_counter

    if embedding_model is None or faiss_index is None:
        logger.error("Embedding model or FAISS index not initialized. Cannot add/update service in FAISS.")
        return

    logger.info(f"Attempting to add/update service '{service_path}' in FAISS.")
    text_to_embed = _get_text_for_embedding(server_info)
    
    current_faiss_id = -1
    needs_new_embedding = True # Assume new embedding is needed

    existing_entry = faiss_metadata_store.get(service_path)

    if existing_entry:
        current_faiss_id = existing_entry["id"]
        if existing_entry.get("text_for_embedding") == text_to_embed:
            needs_new_embedding = False
            logger.info(f"Text for embedding for '{service_path}' has not changed. Will update metadata store only if server_info differs.")
        else:
            logger.info(f"Text for embedding for '{service_path}' has changed. Re-embedding required.")
    else: # New service
        current_faiss_id = next_faiss_id_counter
        next_faiss_id_counter += 1
        logger.info(f"New service '{service_path}'. Assigning new FAISS ID: {current_faiss_id}.")
        needs_new_embedding = True # Definitely needs embedding

    if needs_new_embedding:
        try:
            # Run model encoding in a separate thread to avoid blocking asyncio event loop
            embedding = await asyncio.to_thread(embedding_model.encode, [text_to_embed])
            embedding_np = np.array([embedding[0]], dtype=np.float32)
            
            ids_to_remove = np.array([current_faiss_id])
            if existing_entry: # Only attempt removal if it was an existing entry
                try:
                    # remove_ids returns number of vectors removed.
                    # It's okay if the ID isn't found (returns 0).
                    num_removed = faiss_index.remove_ids(ids_to_remove)
                    if num_removed > 0:
                        logger.info(f"Removed {num_removed} old vector(s) for FAISS ID {current_faiss_id} ({service_path}).")
                    else:
                        logger.info(f"No old vector found for FAISS ID {current_faiss_id} ({service_path}) during update, or ID not in index.")
                except Exception as e_remove: # Should be rare with IndexIDMap if ID was valid type
                    logger.warning(f"Issue removing FAISS ID {current_faiss_id} for {service_path}: {e_remove}. Proceeding to add.")
            
            faiss_index.add_with_ids(embedding_np, np.array([current_faiss_id]))
            logger.info(f"Added/Updated vector for '{service_path}' with FAISS ID {current_faiss_id}.")
        except Exception as e:
            logger.error(f"Error encoding or adding embedding for '{service_path}': {e}", exc_info=True)
            return # Don't update metadata or save if embedding failed

    # Update metadata store if new, or if text changed, or if full_server_info changed
    # --- Enrich server_info with is_enabled status before storing --- START
    enriched_server_info = server_info.copy()
    enriched_server_info["is_enabled"] = MOCK_SERVICE_STATE.get(service_path, False) # Default to False if not found
    # --- Enrich server_info with is_enabled status before storing --- END

    if existing_entry is None or needs_new_embedding or existing_entry.get("full_server_info") != enriched_server_info:
        faiss_metadata_store[service_path] = {
            "id": current_faiss_id,
            "text_for_embedding": text_to_embed,
            "full_server_info": enriched_server_info # Store the enriched server_info
        }
        logger.debug(f"Updated faiss_metadata_store for '{service_path}'.")
        await asyncio.to_thread(save_faiss_data) # Persist changes in a thread
    else:
        logger.debug(f"No changes to FAISS vector or enriched full_server_info for '{service_path}'. Skipping save.")

# --- FAISS Helper Functions --- END

async def broadcast_health_status():
    """Sends the current health status to all connected WebSocket clients."""
    if active_connections:
        logger.info(f"Broadcasting health status to {len(active_connections)} clients...")

        # Construct data payload with status and ISO timestamp string
        data_to_send = {}
        for path, status in SERVER_HEALTH_STATUS.items():
            last_checked_dt = SERVER_LAST_CHECK_TIME.get(path)
            # Send ISO string or None
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            # Get the current tool count from REGISTERED_SERVERS
            num_tools = REGISTERED_SERVERS.get(path, {}).get("num_tools", 0) # Default to 0 if not found

            data_to_send[path] = {
                "status": status,
                "last_checked_iso": last_checked_iso, # Changed key
                "num_tools": num_tools # --- Add num_tools --- START
            }
            # --- Add num_tools --- END

        message = json.dumps(data_to_send)

        # Keep track of connections that fail during send
        disconnected_clients = set()

        # Iterate over a copy of the set to allow modification during iteration
        current_connections = list(active_connections)

        # Create send tasks and associate them with the connection
        send_tasks = []
        for conn in current_connections:
            send_tasks.append((conn, conn.send_text(message)))

        # Run tasks concurrently and check results
        results = await asyncio.gather(*(task for _, task in send_tasks), return_exceptions=True)

        for i, result in enumerate(results):
            conn, _ = send_tasks[i] # Get the corresponding connection
            if isinstance(result, Exception):
                # Check if it's a connection-related error (more specific checks possible)
                # For now, assume any exception during send means the client is gone
                logger.warning(f"Error sending to WebSocket client {conn.client}: {result}. Marking for removal.")
                disconnected_clients.add(conn)

        # Remove all disconnected clients identified during the broadcast
        if disconnected_clients:
            logger.info(f"Removing {len(disconnected_clients)} disconnected clients after broadcast.")
            for conn in disconnected_clients:
                if conn in active_connections:
                    active_connections.remove(conn)

# Session management configuration
# Session management configuration
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    # Generate a secure random key (32 bytes = 256 bits of entropy)
    SECRET_KEY = secrets.token_hex(32)
    logger.warning("No SECRET_KEY environment variable found. Using a randomly generated key. "
                   "While this is more secure than a hardcoded default, it will change on restart. "
                   "Set a permanent SECRET_KEY environment variable for production.")
SESSION_COOKIE_NAME = "mcp_gateway_session"
signer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_MAX_AGE_SECONDS = 60 * 60 * 8  # 8 hours

# --- Nginx Config Generation ---

LOCATION_BLOCK_TEMPLATE = """
    location {path}/ {{
        proxy_pass {proxy_pass_url};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
"""

COMMENTED_LOCATION_BLOCK_TEMPLATE = """
#    location {path}/ {{
#        proxy_pass {proxy_pass_url};
#        proxy_http_version 1.1;
#        proxy_set_header Host $host;
#        proxy_set_header X-Real-IP $remote_addr;
#        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#        proxy_set_header X-Forwarded-Proto $scheme;
#    }}
"""

def regenerate_nginx_config():
    """Generates the nginx config file based on registered servers and their state."""
    logger.info(f"Attempting to directly modify Nginx config at {NGINX_CONFIG_PATH}...")
    
    # Define markers
    START_MARKER = "# DYNAMIC_LOCATIONS_START"
    END_MARKER = "# DYNAMIC_LOCATIONS_END"

    try:
        # Read the *target* Nginx config file
        with open(NGINX_CONFIG_PATH, 'r') as f_target:
            target_content = f_target.read()

        # Generate the location blocks section content (only needs to be done once)
        location_blocks_content = []
        sorted_paths = sorted(REGISTERED_SERVERS.keys())

        for path in sorted_paths:
            server_info = REGISTERED_SERVERS[path]
            proxy_url = server_info.get("proxy_pass_url")
            is_enabled = MOCK_SERVICE_STATE.get(path, False)
            health_status = SERVER_HEALTH_STATUS.get(path)

            if not proxy_url:
                logger.warning(f"Skipping server '{server_info['server_name']}' ({path}) - missing proxy_pass_url.")
                continue

            if is_enabled and health_status == "healthy":
                block = LOCATION_BLOCK_TEMPLATE.format(path=path, proxy_pass_url=proxy_url)
            else:
                block = COMMENTED_LOCATION_BLOCK_TEMPLATE.format(path=path, proxy_pass_url=proxy_url)
            location_blocks_content.append(block)
        
        generated_section = "\n".join(location_blocks_content).strip()

        # --- Replace content between ALL marker pairs --- START
        new_content = ""
        current_pos = 0
        while True:
            # Find the next start marker
            start_index = target_content.find(START_MARKER, current_pos)
            if start_index == -1:
                # No more start markers found, append the rest of the file
                new_content += target_content[current_pos:]
                break

            # Find the corresponding end marker after the start marker
            end_index = target_content.find(END_MARKER, start_index + len(START_MARKER))
            if end_index == -1:
                # Found a start marker without a matching end marker, log error and stop
                logger.error(f"Found '{START_MARKER}' at position {start_index} without a matching '{END_MARKER}' in {NGINX_CONFIG_PATH}. Aborting regeneration.")
                # Append the rest of the file to avoid data loss, but don't reload
                new_content += target_content[current_pos:] 
                # Write back the partially processed content? Or just return False?
                # Let's return False to indicate failure without modifying the file potentially incorrectly.
                return False # Indicate failure
            
            # Append the content before the current start marker
            new_content += target_content[current_pos:start_index + len(START_MARKER)]
            # Append the newly generated section (with appropriate newlines)
            new_content += f"\n\n{generated_section}\n\n    "
            # Update current position to be after the end marker
            current_pos = end_index
        
        # Check if any replacements were made (i.e., if current_pos moved beyond 0)
        if current_pos == 0:
             logger.error(f"No marker pairs '{START_MARKER}'...'{END_MARKER}' found in {NGINX_CONFIG_PATH}. Cannot regenerate.")
             return False

        final_config = new_content # Use the iteratively built content
        # --- Replace content between ALL marker pairs --- END

        # # Find the start and end markers in the target content
        # start_index = target_content.find(START_MARKER)
        # end_index = target_content.find(END_MARKER)
        #
        # if start_index == -1 or end_index == -1 or end_index <= start_index:
        #     logger.error(f"Markers '{START_MARKER}' and/or '{END_MARKER}' not found or in wrong order in {NGINX_CONFIG_PATH}. Cannot regenerate.")
        #     return False
        # 
        # # Extract the parts before the start marker and after the end marker
        # prefix = target_content[:start_index + len(START_MARKER)]
        # suffix = target_content[end_index:]
        #
        # # Construct the new content
        # # Add newlines around the generated section for readability
        # final_config = f"{prefix}\n\n{generated_section}\n\n    {suffix}"

        # Write the modified content back to the target file
        with open(NGINX_CONFIG_PATH, 'w') as f_out:
            f_out.write(final_config)
        logger.info(f"Nginx config file {NGINX_CONFIG_PATH} modified successfully.")

        # --- Reload Nginx --- START
        try:
            logger.info("Attempting to reload Nginx configuration...")
            result = subprocess.run(['/usr/sbin/nginx', '-s', 'reload'], check=True, capture_output=True, text=True)
            logger.info(f"Nginx reload successful. stdout: {result.stdout.strip()}")
            return True
        except FileNotFoundError:
            logger.error("'nginx' command not found. Cannot reload configuration.")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to reload Nginx configuration. Return code: {e.returncode}")
            logger.error(f"Nginx reload stderr: {e.stderr.strip()}")
            logger.error(f"Nginx reload stdout: {e.stdout.strip()}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during Nginx reload: {e}", exc_info=True)
            return False
        # --- Reload Nginx --- END

    except FileNotFoundError:
        logger.error(f"Target Nginx config file not found at {NGINX_CONFIG_PATH}. Cannot regenerate.")
        return False
    except Exception as e:
        logger.error(f"Failed to modify Nginx config at {NGINX_CONFIG_PATH}: {e}", exc_info=True)
        return False

# --- Helper function to normalize a path to a filename ---
def path_to_filename(path):
    # Remove leading slash and replace remaining slashes with underscores
    normalized = path.lstrip("/").replace("/", "_")
    # Append .json extension if not present
    if not normalized.endswith(".json"):
        normalized += ".json"
    return normalized


# --- Data Loading ---
def load_registered_servers_and_state():
    global REGISTERED_SERVERS, MOCK_SERVICE_STATE
    logger.info(f"Loading server definitions from {SERVERS_DIR}...")

    # Create servers directory if it doesn't exist
    SERVERS_DIR.mkdir(parents=True, exist_ok=True) # Added parents=True

    temp_servers = {}
    server_files = list(SERVERS_DIR.glob("**/*.json"))
    logger.info(f"Found {len(server_files)} JSON files in {SERVERS_DIR} and its subdirectories")
    for file in server_files:
        logger.info(f"[DEBUG] - {file.relative_to(SERVERS_DIR)}")

    if not server_files:
        logger.warning(f"No server definition files found in {SERVERS_DIR}. Initializing empty registry.")
        REGISTERED_SERVERS = {}
        # Don't return yet, need to load state file
        # return

    for server_file in server_files:
        if server_file.name == STATE_FILE_PATH.name: # Skip the state file itself
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

                    # Add new fields with defaults
                    server_info["description"] = server_info.get("description", "")
                    server_info["tags"] = server_info.get("tags", [])
                    server_info["num_tools"] = server_info.get("num_tools", 0)
                    server_info["num_stars"] = server_info.get("num_stars", 0)
                    server_info["is_python"] = server_info.get("is_python", False)
                    server_info["license"] = server_info.get("license", "N/A")
                    server_info["proxy_pass_url"] = server_info.get("proxy_pass_url", None)
                    server_info["tool_list"] = server_info.get("tool_list", []) # Initialize tool_list if missing

                    temp_servers[server_path] = server_info
                else:
                    logger.warning(f"Invalid server entry format found in {server_file}. Skipping.")
        except FileNotFoundError:
            logger.error(f"Server definition file {server_file} reported by glob not found.")
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from {server_file}: {e}.")
        except Exception as e:
            logger.error(f"An unexpected error occurred loading {server_file}: {e}", exc_info=True)

    REGISTERED_SERVERS = temp_servers
    logger.info(f"Successfully loaded {len(REGISTERED_SERVERS)} server definitions.")

    # --- Load persisted mock service state --- START
    logger.info(f"Attempting to load persisted state from {STATE_FILE_PATH}...")
    loaded_state = {}
    try:
        if STATE_FILE_PATH.exists():
            with open(STATE_FILE_PATH, "r") as f:
                loaded_state = json.load(f)
            if not isinstance(loaded_state, dict):
                logger.warning(f"Invalid state format in {STATE_FILE_PATH}. Expected a dictionary. Resetting state.")
                loaded_state = {} # Reset if format is wrong
            else:
                logger.info("Successfully loaded persisted state.")
        else:
            logger.info(f"No persisted state file found at {STATE_FILE_PATH}. Initializing state.")

    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON from {STATE_FILE_PATH}: {e}. Initializing empty state.")
        loaded_state = {}
    except Exception as e:
        logger.error(f"Failed to read state file {STATE_FILE_PATH}: {e}. Initializing empty state.", exc_info=True)
        loaded_state = {}

    # Initialize MOCK_SERVICE_STATE: Use loaded state if valid, otherwise default to False.
    # Ensure state only contains keys for currently registered servers.
    MOCK_SERVICE_STATE = {}
    for path in REGISTERED_SERVERS.keys():
        MOCK_SERVICE_STATE[path] = loaded_state.get(path, False) # Default to False if not in loaded state or state was invalid

    logger.info(f"Initial mock service state loaded: {MOCK_SERVICE_STATE}")
    # --- Load persisted mock service state --- END


    # Initialize health status to 'checking' or 'disabled' based on the just loaded state
    global SERVER_HEALTH_STATUS
    SERVER_HEALTH_STATUS = {} # Start fresh
    for path, is_enabled in MOCK_SERVICE_STATE.items():
        if path in REGISTERED_SERVERS: # Should always be true here now
            SERVER_HEALTH_STATUS[path] = "checking" if is_enabled else "disabled"
        else:
             # This case should ideally not happen if MOCK_SERVICE_STATE is built from REGISTERED_SERVERS
             logger.warning(f"Path {path} found in loaded state but not in registered servers. Ignoring.")

    logger.info(f"Initialized health status based on loaded state: {SERVER_HEALTH_STATUS}")

    # We no longer need the explicit default initialization block below
    # print("Initializing mock service state (defaulting to disabled)...")
    # MOCK_SERVICE_STATE = {path: False for path in REGISTERED_SERVERS.keys()}
    # # TODO: Consider loading initial state from a persistent store if needed
    # print(f"Initial mock state: {MOCK_SERVICE_STATE}")


# --- Helper function to save server data ---
def save_server_to_file(server_info):
    try:
        # Create servers directory if it doesn't exist
        SERVERS_DIR.mkdir(parents=True, exist_ok=True) # Ensure it exists

        # Generate filename based on path
        path = server_info["path"]
        filename = path_to_filename(path)
        file_path = SERVERS_DIR / filename

        with open(file_path, "w") as f:
            json.dump(server_info, f, indent=2)

        logger.info(f"Successfully saved server '{server_info['server_name']}' to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save server '{server_info.get('server_name', 'UNKNOWN')}' data to {filename}: {e}", exc_info=True)
        return False


# --- MCP Client Function to Get Tool List --- START (Renamed)
async def get_tools_from_server(base_url: str) -> List[dict] | None: # Return list of dicts
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

# --- MCP Client Function to Get Tool List --- END


# --- Single Health Check Logic ---
async def perform_single_health_check(path: str) -> tuple[str, datetime | None]:
    """Performs a health check for a single service path and updates global state."""
    global SERVER_HEALTH_STATUS, SERVER_LAST_CHECK_TIME, REGISTERED_SERVERS # Ensure REGISTERED_SERVERS is global

    server_info = REGISTERED_SERVERS.get(path)
    # --- Store previous status --- START
    previous_status = SERVER_HEALTH_STATUS.get(path) # Get status before check
    # --- Store previous status --- END

    if not server_info:
        # Should not happen if called correctly, but handle defensively
        return "error: server not registered", None

    url = server_info.get("proxy_pass_url")
    is_enabled = MOCK_SERVICE_STATE.get(path, False) # Get enabled state for later check

    # --- Record check time ---
    last_checked_time = datetime.now(timezone.utc)
    SERVER_LAST_CHECK_TIME[path] = last_checked_time
    # --- Record check time ---

    if not url:
        current_status = "error: missing URL"
        SERVER_HEALTH_STATUS[path] = current_status
        logger.info(f"Health check skipped for {path}: Missing URL.")
        # --- Regenerate Nginx if status affecting it changed --- START
        if is_enabled and previous_status == "healthy": # Was healthy, now isn't (due to missing URL)
             logger.info(f"Status changed from healthy for {path}, regenerating Nginx config...")
             regenerate_nginx_config()
        # --- Regenerate Nginx if status affecting it changed --- END
        return current_status, last_checked_time

    # Update status to 'checking' before performing the check
    # Only print if status actually changes to 'checking'
    if previous_status != "checking":
        logger.info(f"Setting status to 'checking' for {path} ({url})...")
        SERVER_HEALTH_STATUS[path] = "checking"
        # Optional: Consider a targeted broadcast here if immediate 'checking' feedback is desired
        # await broadcast_specific_update(path, "checking", last_checked_time)

    # --- Append /sse to the health check URL --- START
    health_check_url = url.rstrip('/') + "/sse"
    # --- Append /sse to the health check URL --- END

    # cmd = ['curl', '--head', '-s', '-f', '--max-time', str(HEALTH_CHECK_TIMEOUT_SECONDS), url]
    cmd = ['curl', '--head', '-s', '-f', '--max-time', str(HEALTH_CHECK_TIMEOUT_SECONDS), health_check_url] # Use modified URL
    current_status = "checking" # Status will be updated below

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Use a slightly longer timeout for wait_for to catch process hangs
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS + 2)
        stderr_str = stderr.decode().strip() if stderr else ''

        if proc.returncode == 0:
            current_status = "healthy"
            logger.info(f"Health check successful for {path} ({url}).")

            # --- Check for transition to healthy state --- START
            # Note: Tool list fetching moved inside the status transition check
            if previous_status != "healthy":
                logger.info(f"Service {path} transitioned to healthy. Regenerating Nginx config and fetching tool list...")
                 # --- Regenerate Nginx on transition TO healthy --- START
                regenerate_nginx_config()
                 # --- Regenerate Nginx on transition TO healthy --- END

                # Ensure url is not None before attempting connection (redundant check as url is checked above, but safe)
                if url:
                    tool_list = await get_tools_from_server(url) # Get the list of dicts

                    if tool_list is not None: # Check if list retrieval was successful
                        new_tool_count = len(tool_list)
                        # Get current list (now list of dicts)
                        current_tool_list = REGISTERED_SERVERS[path].get("tool_list", [])
                        current_tool_count = REGISTERED_SERVERS[path].get("num_tools", 0)

                        # Compare lists more carefully (simple set comparison won't work on dicts)
                        # Convert to comparable format (e.g., sorted list of JSON strings)
                        current_tool_list_str = sorted([json.dumps(t, sort_keys=True) for t in current_tool_list])
                        new_tool_list_str = sorted([json.dumps(t, sort_keys=True) for t in tool_list])

                        # if set(current_tool_list) != set(tool_list) or current_tool_count != new_tool_count:
                        if current_tool_list_str != new_tool_list_str or current_tool_count != new_tool_count:
                            logger.info(f"Updating tool list for {path}. New count: {new_tool_count}.") # Simplified log
                            REGISTERED_SERVERS[path]["tool_list"] = tool_list # Store the new list of dicts
                            REGISTERED_SERVERS[path]["num_tools"] = new_tool_count # Update the count
                            # Save the updated server info to its file
                            if not save_server_to_file(REGISTERED_SERVERS[path]):
                                logger.error(f"ERROR: Failed to save updated tool list/count for {path} to file.")
                            # --- Update FAISS after tool list/count change --- START
                            # No explicit call here, will be handled by the one at the end of perform_single_health_check
                            # logger.info(f"Updating FAISS metadata for '{path}' after tool list/count update.")
                            # await add_or_update_service_in_faiss(path, REGISTERED_SERVERS[path]) # Moved to end
                            # --- Update FAISS after tool list/count change --- END
                        else:
                             logger.info(f"Tool list for {path} remains unchanged. No update needed.")
                    else:
                        logger.info(f"Failed to retrieve tool list for healthy service {path}. List/Count remains unchanged.")
                        # Even if tool list fetch failed, server is healthy.
                        # FAISS update will occur at the end of this function with current REGISTERED_SERVERS[path].
                else:
                    # This case should technically not be reachable due to earlier url check
                    logger.info(f"Cannot fetch tool list for {path}: proxy_pass_url is missing.")
            # --- Check for transition to healthy state --- END
            # If it was already healthy, and tools changed, the above block (current_tool_list_str != new_tool_list_str) handles it.
            # The FAISS update with the latest REGISTERED_SERVERS[path] will happen at the end of this function.

        elif proc.returncode == 28:
            current_status = f"error: timeout ({HEALTH_CHECK_TIMEOUT_SECONDS}s)"
            logger.info(f"Health check timeout for {path} ({url})")
        elif proc.returncode == 22: # HTTP error >= 400
            current_status = "unhealthy (HTTP error)"
            logger.info(f"Health check unhealthy (HTTP >= 400) for {path} ({url}). Stderr: {stderr_str}")
        elif proc.returncode == 7: # Connection failed
            current_status = "error: connection failed"
            logger.info(f"Health check connection failed for {path} ({url}). Stderr: {stderr_str}")
        else: # Other curl errors
            error_msg = f"error: check failed (code {proc.returncode})"
            if stderr_str:
                error_msg += f" - {stderr_str}"
            current_status = error_msg
            logger.info(f"Health check failed for {path} ({url}): {error_msg}")

    except asyncio.TimeoutError:
        # This catches timeout on asyncio.wait_for, slightly different from curl's --max-time
        current_status = "error: check process timeout"
        logger.info(f"Health check asyncio.wait_for timeout for {path} ({url})")
    except FileNotFoundError:
        current_status = "error: command not found"
        logger.error(f"ERROR: 'curl' command not found during health check for {path}. Cannot perform check.")
        # No need to stop all checks, just this one fails
    except Exception as e:
        current_status = f"error: {type(e).__name__}"
        logger.error(f"ERROR: Unexpected error during health check for {path} ({url}): {e}")

    # Update the global status *after* the check completes
    SERVER_HEALTH_STATUS[path] = current_status
    logger.info(f"Final health status for {path}: {current_status}")

    # --- Update FAISS with final server_info state after health check attempt ---
    if path in REGISTERED_SERVERS and embedding_model and faiss_index is not None:
        logger.info(f"Updating FAISS metadata for '{path}' post health check (status: {current_status}).")
        await add_or_update_service_in_faiss(path, REGISTERED_SERVERS[path])

    # --- Regenerate Nginx if status affecting it changed --- START
    # Check if the service is enabled AND its Nginx-relevant status changed
    if is_enabled:
        if previous_status == "healthy" and current_status != "healthy":
            logger.info(f"Status changed FROM healthy for enabled service {path}, regenerating Nginx config...")
            regenerate_nginx_config()
        # Regeneration on transition TO healthy is handled within the proc.returncode == 0 block above
        # elif previous_status != "healthy" and current_status == "healthy":
        #     print(f"Status changed TO healthy for {path}, regenerating Nginx config...")
        #     regenerate_nginx_config() # Already handled above
    # --- Regenerate Nginx if status affecting it changed --- END


    return current_status, last_checked_time


# --- Background Health Check Task ---
async def run_health_checks():
    """Periodically checks the health of registered *enabled* services."""
    while True:
        logger.info(f"Running periodic health checks (Interval: {HEALTH_CHECK_INTERVAL_SECONDS}s)...")
        paths_to_check = list(REGISTERED_SERVERS.keys())
        needs_broadcast = False # Flag to check if any status actually changed

        # --- Use a copy of MOCK_SERVICE_STATE for stable iteration --- START
        current_enabled_state = MOCK_SERVICE_STATE.copy()
        # --- Use a copy of MOCK_SERVICE_STATE for stable iteration --- END

        for path in paths_to_check:
            if path not in REGISTERED_SERVERS: # Check if server was removed during the loop
                continue

            # --- Use copied state for check --- START
            # is_enabled = MOCK_SERVICE_STATE.get(path, False)
            is_enabled = current_enabled_state.get(path, False)
            # --- Use copied state for check --- END
            previous_status = SERVER_HEALTH_STATUS.get(path)

            if not is_enabled:
                new_status = "disabled"
                if previous_status != new_status:
                    SERVER_HEALTH_STATUS[path] = new_status
                    # Also clear last check time when disabling? Or keep it? Keep for now.
                    # SERVER_LAST_CHECK_TIME[path] = None
                    needs_broadcast = True
                    logger.info(f"Service {path} is disabled. Setting status.")
                continue # Skip health check for disabled services

            # --- Service is enabled, perform check using the new function ---
            logger.info(f"Performing periodic check for enabled service: {path}")
            try:
                # Call the refactored check function
                # We only care if the status *changed* from the beginning of the cycle for broadcast purposes
                current_status, _ = await perform_single_health_check(path)
                if previous_status != current_status:
                    needs_broadcast = True
            except Exception as e:
                # Log error if the check function itself fails unexpectedly
                logger.error(f"ERROR: Unexpected exception calling perform_single_health_check for {path}: {e}")
                # Update status to reflect this error?
                error_status = f"error: check execution failed ({type(e).__name__})"
                if previous_status != error_status:
                    SERVER_HEALTH_STATUS[path] = error_status
                    SERVER_LAST_CHECK_TIME[path] = datetime.now(timezone.utc) # Record time of failure
                    needs_broadcast = True


        logger.info(f"Finished periodic health checks. Current status map: {SERVER_HEALTH_STATUS}")
        # Broadcast status update only if something changed during this cycle
        if needs_broadcast:
            logger.info("Broadcasting updated health status after periodic check...")
            await broadcast_health_status()
        else:
            logger.info("No status changes detected in periodic check, skipping broadcast.")

        # Wait for the next interval
        await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)


# --- Lifespan for Startup Task ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Configure Logging INSIDE lifespan --- START
    # Ensure log directory exists
    CONTAINER_LOG_DIR.mkdir(parents=True, exist_ok=True) # Should be defined now

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH), # Use correct variable
            logging.StreamHandler() # Log to console (stdout/stderr)
        ]
    )
    logger.info("Logging configured. Running startup tasks...") # Now logger is configured
    # --- Configure Logging INSIDE lifespan --- END

    # 0. Load FAISS data and embedding model
    load_faiss_data() # Loads model, empty index or existing index. Synchronous.

    # 1. Load server definitions and persisted enabled/disabled state
    load_registered_servers_and_state() # This populates REGISTERED_SERVERS. Synchronous.

    # 1.5 Sync FAISS with loaded servers (initial build or update)
    if embedding_model and faiss_index is not None: # Check faiss_index is not None
        logger.info("Performing initial FAISS synchronization with loaded server definitions...")
        sync_tasks = []
        for path, server_info in REGISTERED_SERVERS.items():
            # add_or_update_service_in_faiss is async, can be gathered
            sync_tasks.append(add_or_update_service_in_faiss(path, server_info))
        
        if sync_tasks:
            await asyncio.gather(*sync_tasks)
        logger.info("Initial FAISS synchronization complete.")
    else:
        logger.warning("Skipping initial FAISS synchronization: embedding model or FAISS index not ready.")

    # 2. Perform initial health checks concurrently for *enabled* services
    logger.info("Performing initial health checks for enabled services...")
    initial_check_tasks = []
    enabled_paths = [path for path, is_enabled in MOCK_SERVICE_STATE.items() if is_enabled]

    global SERVER_HEALTH_STATUS, SERVER_LAST_CHECK_TIME
    # Initialize status for all servers (defaults for disabled)
    for path in REGISTERED_SERVERS.keys():
        SERVER_LAST_CHECK_TIME[path] = None # Initialize last check time
        if path not in enabled_paths:
             SERVER_HEALTH_STATUS[path] = "disabled"
        else:
             # Will be set by the check task below (or remain unset if check fails badly)
             SERVER_HEALTH_STATUS[path] = "checking" # Tentative status before check runs

    logger.info(f"Initially enabled services to check: {enabled_paths}")
    if enabled_paths:
        for path in enabled_paths:
            # Create a task for each enabled service check
            task = asyncio.create_task(perform_single_health_check(path))
            initial_check_tasks.append(task)

        # Wait for all initial checks to complete
        results = await asyncio.gather(*initial_check_tasks, return_exceptions=True)

        # Log results/errors from initial checks
        for i, result in enumerate(results):
            path = enabled_paths[i]
            if isinstance(result, Exception):
                logger.error(f"ERROR during initial health check for {path}: {result}")
                # Status might have already been set to an error state within the check function
            else:
                status, _ = result # Unpack the result tuple
                logger.info(f"Initial health check completed for {path}: Status = {status}")
                # Update FAISS with potentially changed server_info (e.g., num_tools from health check)
                if path in REGISTERED_SERVERS and embedding_model and faiss_index is not None:
                     # This runs after each health check result, can be awaited individually
                    await add_or_update_service_in_faiss(path, REGISTERED_SERVERS[path])
    else:
        logger.info("No services are initially enabled.")

    logger.info(f"Initial health status after checks: {SERVER_HEALTH_STATUS}")

    # 3. Generate Nginx config *after* initial checks are done
    logger.info("Generating initial Nginx configuration...")
    regenerate_nginx_config() # Generate config based on initial health status

    # 4. Start the background periodic health check task
    logger.info("Starting background health check task...")
    health_check_task = asyncio.create_task(run_health_checks())

    # --- Yield to let the application run --- START
    yield
    # --- Yield to let the application run --- END

    # --- Shutdown tasks --- START
    logger.info("Running shutdown tasks...")
    logger.info("Cancelling background health check task...")
    health_check_task.cancel()
    try:
        await health_check_task
    except asyncio.CancelledError:
        logger.info("Health check task cancelled successfully.")
    # --- Shutdown tasks --- END


app = FastAPI(lifespan=lifespan)


# --- Authentication / Session Dependency ---
def get_current_user(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> str:
    if session is None:
        raise HTTPException(
            status_code=307, detail="Not authenticated", headers={"Location": "/login"}
        )
    try:
        data = signer.loads(session, max_age=SESSION_MAX_AGE_SECONDS)
        username = data.get("username")
        if not username:
            raise HTTPException(
                status_code=307,
                detail="Invalid session data",
                headers={"Location": "/login"},
            )
        return username
    except (BadSignature, SignatureExpired):
        response = RedirectResponse(
            url="/login?error=Session+expired+or+invalid", status_code=307
        )
        response.delete_cookie(SESSION_COOKIE_NAME)
        raise HTTPException(
            status_code=307,
            detail="Session expired or invalid",
            headers={"Location": "/login"},
        )
    except Exception:
        raise HTTPException(
            status_code=307,
            detail="Authentication error",
            headers={"Location": "/login"},
        )


# --- API Authentication Dependency (returns 401 instead of redirecting) ---
def api_auth(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> str:
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        data = signer.loads(session, max_age=SESSION_MAX_AGE_SECONDS)
        username = data.get("username")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid session data")
        return username
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication error")


# --- Static Files and Templates (Paths relative to this script) ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- Routes ---


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@app.post("/login")
async def login_submit(
    username: Annotated[str, Form()], password: Annotated[str, Form()]
):
    # cu = os.environ.get("ADMIN_USER", "admin")
    # cp = os.environ.get("ADMIN_PASSWORD", "password")
    # logger.info(f"Login attempt with username: {username}, {cu}")
    # logger.info(f"Login attempt with password: {password}, {cp}")
    correct_username = secrets.compare_digest(
        username, os.environ.get("ADMIN_USER", "admin")
    )
    correct_password = secrets.compare_digest(
        password, os.environ.get("ADMIN_PASSWORD", "password")
    )
    if correct_username and correct_password:
        session_data = signer.dumps({"username": username})
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_data,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
        logger.info(f"User '{username}' logged in successfully.")
        return response
    else:
        logger.info(f"Login failed for user '{username}'.")
        return RedirectResponse(
            url="/login?error=Invalid+username+or+password",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@app.post("/logout")
async def logout():
    logger.info("User logged out.")
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    username: Annotated[str, Depends(get_current_user)],
    query: str | None = None,
):
    service_data = []
    search_query = query.lower() if query else ""
    sorted_server_paths = sorted(
        REGISTERED_SERVERS.keys(), key=lambda p: REGISTERED_SERVERS[p]["server_name"]
    )
    for path in sorted_server_paths:
        server_info = REGISTERED_SERVERS[path]
        server_name = server_info["server_name"]
        # Include description and tags in search
        searchable_text = f"{server_name.lower()} {server_info.get('description', '').lower()} {' '.join(server_info.get('tags', []))}"
        if not search_query or search_query in searchable_text:
            # Pass all required fields to the template
            service_data.append(
                {
                    "display_name": server_name,
                    "path": path,
                    "description": server_info.get("description", ""),
                    "is_enabled": MOCK_SERVICE_STATE.get(path, False),
                    "tags": server_info.get("tags", []),
                    "num_tools": server_info.get("num_tools", 0),
                    "num_stars": server_info.get("num_stars", 0),
                    "is_python": server_info.get("is_python", False),
                    "license": server_info.get("license", "N/A"),
                    "health_status": SERVER_HEALTH_STATUS.get(path, "unknown"), # Get current health status
                    "last_checked_iso": SERVER_LAST_CHECK_TIME.get(path).isoformat() if SERVER_LAST_CHECK_TIME.get(path) else None
                }
            )
    # --- End Debug ---
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "services": service_data, "username": username},
    )


@app.post("/toggle/{service_path:path}")
async def toggle_service_route(
    request: Request,
    service_path: str,
    enabled: Annotated[str | None, Form()] = None,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    if not service_path.startswith("/"):
        service_path = "/" + service_path
    if service_path not in REGISTERED_SERVERS:
        raise HTTPException(status_code=404, detail="Service path not registered")

    new_state = enabled == "on"
    MOCK_SERVICE_STATE[service_path] = new_state
    server_name = REGISTERED_SERVERS[service_path]["server_name"]
    logger.info(
        f"Simulated toggle for '{server_name}' ({service_path}) to {new_state} by user '{username}'"
    )

    # --- Update health status immediately on toggle --- START
    new_status = ""
    last_checked_iso = None
    last_checked_dt = None # Initialize datetime object

    if new_state:
        # Perform immediate check when enabling
        logger.info(f"Performing immediate health check for {service_path} upon toggle ON...")
        try:
            new_status, last_checked_dt = await perform_single_health_check(service_path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(f"Immediate check for {service_path} completed. Status: {new_status}")
        except Exception as e:
            # Handle potential errors during the immediate check itself
            logger.error(f"ERROR during immediate health check for {service_path}: {e}")
            new_status = f"error: immediate check failed ({type(e).__name__})"
            # Update global state to reflect this error
            SERVER_HEALTH_STATUS[service_path] = new_status
            last_checked_dt = SERVER_LAST_CHECK_TIME.get(service_path) # Use time if check started
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
    else:
        # When disabling, set status to disabled and keep last check time
        new_status = "disabled"
        # Keep the last check time from when it was enabled
        last_checked_dt = SERVER_LAST_CHECK_TIME.get(service_path)
        last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
        # Update global state directly when disabling
        SERVER_HEALTH_STATUS[service_path] = new_status
        logger.info(f"Service {service_path} toggled OFF. Status set to disabled.")
        # --- Update FAISS metadata for disabled service --- START
        if embedding_model and faiss_index is not None:
            logger.info(f"Updating FAISS metadata for disabled service {service_path}.")
            # REGISTERED_SERVERS[service_path] contains the static definition
            await add_or_update_service_in_faiss(service_path, REGISTERED_SERVERS[service_path])
        else:
            logger.warning(f"Skipped FAISS metadata update for disabled service {service_path}: model or index not ready.")
        # --- Update FAISS metadata for disabled service --- END

    # --- Send *targeted* update via WebSocket --- START
    # Send immediate feedback for the toggled service only
    # Always get the latest num_tools from the registry
    current_num_tools = REGISTERED_SERVERS.get(service_path, {}).get("num_tools", 0)

    update_data = {
        service_path: {
            "status": new_status,
            "last_checked_iso": last_checked_iso,
            "num_tools": current_num_tools # Include num_tools
        }
    }
    message = json.dumps(update_data)
    logger.info(f"--- TOGGLE: Sending targeted update: {message}")

    # Create task to send without blocking the request
    async def send_specific_update():
        disconnected_clients = set()
        current_connections = list(active_connections)
        send_tasks = []
        for conn in current_connections:
            send_tasks.append((conn, conn.send_text(message)))

        results = await asyncio.gather(*(task for _, task in send_tasks), return_exceptions=True)

        for i, result in enumerate(results):
            conn, _ = send_tasks[i]
            if isinstance(result, Exception):
                logger.warning(f"Error sending toggle update to WebSocket client {conn.client}: {result}. Marking for removal.")
                disconnected_clients.add(conn)
        if disconnected_clients:
            logger.info(f"Removing {len(disconnected_clients)} disconnected clients after toggle update.")
            for conn in disconnected_clients:
                if conn in active_connections:
                    active_connections.remove(conn)

    asyncio.create_task(send_specific_update())
    # --- Send *targeted* update via WebSocket --- END

    # --- Persist the updated state --- START
    try:
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(MOCK_SERVICE_STATE, f, indent=2)
        logger.info(f"Persisted state to {STATE_FILE_PATH}")
    except Exception as e:
        logger.error(f"ERROR: Failed to persist state to {STATE_FILE_PATH}: {e}")
        # Decide if we should raise an error or just log
    # --- Persist the updated state --- END

    # Regenerate Nginx config after toggling state
    if not regenerate_nginx_config():
        logger.error("ERROR: Failed to update Nginx configuration after toggle.")

    # --- Return JSON instead of Redirect --- START
    final_status = SERVER_HEALTH_STATUS.get(service_path, "unknown")
    final_last_checked_dt = SERVER_LAST_CHECK_TIME.get(service_path)
    final_last_checked_iso = final_last_checked_dt.isoformat() if final_last_checked_dt else None
    final_num_tools = REGISTERED_SERVERS.get(service_path, {}).get("num_tools", 0)

    return JSONResponse(
        status_code=200,
        content={
            "message": f"Toggle request for {service_path} processed.",
            "service_path": service_path,
            "new_enabled_state": new_state, # The state it was set to
            "status": final_status, # The status after potential immediate check
            "last_checked_iso": final_last_checked_iso,
            "num_tools": final_num_tools
        }
    )
    # --- Return JSON instead of Redirect --- END

    # query_param = request.query_params.get("query", "")
    # redirect_url = f"/?query={query_param}" if query_param else "/"
    # return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/register")
async def register_service(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    path: Annotated[str, Form()],
    proxy_pass_url: Annotated[str, Form()],
    tags: Annotated[str, Form()] = "",
    num_tools: Annotated[int, Form()] = 0,
    num_stars: Annotated[int, Form()] = 0,
    is_python: Annotated[bool, Form()] = False,
    license_str: Annotated[str, Form(alias="license")] = "N/A",
    username: Annotated[str, Depends(api_auth)] = None,
):
    logger.info("[DEBUG] register_service() called with parameters:")
    logger.info(f"[DEBUG] - name: {name}")
    logger.info(f"[DEBUG] - description: {description}")
    logger.info(f"[DEBUG] - path: {path}")
    logger.info(f"[DEBUG] - proxy_pass_url: {proxy_pass_url}")
    logger.info(f"[DEBUG] - tags: {tags}")
    logger.info(f"[DEBUG] - num_tools: {num_tools}")
    logger.info(f"[DEBUG] - num_stars: {num_stars}")
    logger.info(f"[DEBUG] - is_python: {is_python}")
    logger.info(f"[DEBUG] - license_str: {license_str}")
    logger.info(f"[DEBUG] - username: {username}")

    # Ensure path starts with a slash
    if not path.startswith("/"):
        path = "/" + path
        logger.info(f"[DEBUG] Path adjusted to start with slash: {path}")

    # Check if path already exists
    if path in REGISTERED_SERVERS:
        logger.error(f"[ERROR] Service registration failed: path '{path}' already exists")
        return JSONResponse(
            status_code=400,
            content={"error": f"Service with path '{path}' already exists"},
        )

    # Process tags: split string, strip whitespace, filter empty
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    logger.info(f"[DEBUG] Processed tags: {tag_list}")

    # Create new server entry with all fields
    server_entry = {
        "server_name": name,
        "description": description,
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "tags": tag_list,
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license": license_str,
        "tool_list": [] # Initialize tool list
    }
    logger.info(f"[DEBUG] Created server entry: {json.dumps(server_entry, indent=2)}")

    # Save to individual file
    logger.info("[DEBUG] Attempting to save server data to file...")
    success = save_server_to_file(server_entry)
    if not success:
        logger.error("[ERROR] Failed to save server data to file")
        return JSONResponse(
            status_code=500, content={"error": "Failed to save server data"}
        )
    logger.info("[DEBUG] Successfully saved server data to file")

    # Add to in-memory registry and default to disabled
    logger.info("[DEBUG] Adding server to in-memory registry...")
    REGISTERED_SERVERS[path] = server_entry
    logger.info("[DEBUG] Setting initial service state to disabled")
    MOCK_SERVICE_STATE[path] = False
    # Set initial health status for the new service (always start disabled)
    logger.info("[DEBUG] Setting initial health status to 'disabled'")
    SERVER_HEALTH_STATUS[path] = "disabled" # Start disabled
    SERVER_LAST_CHECK_TIME[path] = None # No check time yet
    # Ensure num_tools is present in the in-memory dict immediately
    if "num_tools" not in REGISTERED_SERVERS[path]:
        logger.info("[DEBUG] Adding missing num_tools field to in-memory registry")
        REGISTERED_SERVERS[path]["num_tools"] = 0

    # Regenerate Nginx config after successful registration
    logger.info("[DEBUG] Attempting to regenerate Nginx configuration...")
    if not regenerate_nginx_config():
        logger.error("[ERROR] Failed to update Nginx configuration after registration")
    else:
        logger.info("[DEBUG] Successfully regenerated Nginx configuration")

    # --- Add to FAISS Index --- START
    logger.info(f"[DEBUG] Adding/updating service '{path}' in FAISS index after registration...")
    if embedding_model and faiss_index is not None:
        await add_or_update_service_in_faiss(path, server_entry) # server_entry is the new service info
        logger.info(f"[DEBUG] Service '{path}' processed for FAISS index.")
    else:
        logger.warning(f"[DEBUG] Skipped FAISS update for '{path}': model or index not ready.")
    # --- Add to FAISS Index --- END

    logger.info(f"[INFO] New service registered: '{name}' at path '{path}' by user '{username}'")

    # --- Persist the updated state after registration --- START
    try:
        logger.info(f"[DEBUG] Attempting to persist state to {STATE_FILE_PATH}...")
        with open(STATE_FILE_PATH, "w") as f:
            json.dump(MOCK_SERVICE_STATE, f, indent=2)
        logger.info(f"[DEBUG] Successfully persisted state to {STATE_FILE_PATH}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to persist state to {STATE_FILE_PATH}: {str(e)}")
    # --- Persist the updated state after registration --- END

    # Broadcast the updated status after registration
    logger.info("[DEBUG] Creating task to broadcast health status...")
    asyncio.create_task(broadcast_health_status())

    logger.info("[DEBUG] Registration complete, returning success response")
    return JSONResponse(
        status_code=201,
        content={
            "message": "Service registered successfully",
            "service": server_entry,
        },
    )

@app.get("/api/server_details/{service_path:path}")
async def get_server_details(
    service_path: str,
    username: Annotated[str, Depends(api_auth)]
):
    # Normalize the path to ensure it starts with '/'
    if not service_path.startswith('/'):
        service_path = '/' + service_path
    
    # Special case: if path is 'all' or '/all', return details for all servers
    if service_path == '/all':
        # Return a dictionary of all registered servers
        return REGISTERED_SERVERS
    
    # Regular case: return details for a specific server
    server_info = REGISTERED_SERVERS.get(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")
    
    # Return the full server info, including proxy_pass_url
    return server_info


# --- Endpoint to get tool list for a service --- START
@app.get("/api/tools/{service_path:path}")
async def get_service_tools(
    service_path: str,
    username: Annotated[str, Depends(api_auth)] # Requires authentication
):
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Handle special case for '/all' to return tools from all servers
    if service_path == '/all':
        all_tools = []
        all_servers_tools = {}
        
        for path, server_info in REGISTERED_SERVERS.items():
            tool_list = server_info.get("tool_list")
            
            if tool_list is not None and isinstance(tool_list, list):
                # Add server information to each tool
                server_tools = []
                for tool in tool_list:
                    # Create a copy of the tool with server info added
                    tool_with_server = dict(tool)
                    tool_with_server["server_path"] = path
                    tool_with_server["server_name"] = server_info.get("server_name", "Unknown")
                    server_tools.append(tool_with_server)
                
                all_tools.extend(server_tools)
                all_servers_tools[path] = server_tools
        
        return {
            "service_path": "all",
            "tools": all_tools,
            "servers": all_servers_tools
        }
    
    # Handle specific server case (existing logic)
    server_info = REGISTERED_SERVERS.get(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    tool_list = server_info.get("tool_list") # Get the stored list

    if tool_list is None:
        # This might happen if the service hasn't become healthy yet
        raise HTTPException(status_code=404, detail="Tool list not available yet. Service may not be healthy or check is pending.")
    elif not isinstance(tool_list, list):
         # Data integrity check
        logger.warning(f"Warning: tool_list for {service_path} is not a list: {type(tool_list)}")
        raise HTTPException(status_code=500, detail="Internal server error: Invalid tool list format.")

    return {"service_path": service_path, "tools": tool_list}
# --- Endpoint to get tool list for a service --- END


# --- Refresh Endpoint --- START
@app.post("/api/refresh/{service_path:path}")
async def refresh_service(service_path: str, username: Annotated[str, Depends(api_auth)]):
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Check if service exists
    if service_path not in REGISTERED_SERVERS:
        raise HTTPException(status_code=404, detail="Service path not registered")

    # Check if service is enabled
    is_enabled = MOCK_SERVICE_STATE.get(service_path, False)
    if not is_enabled:
        raise HTTPException(status_code=400, detail="Cannot refresh a disabled service")

    logger.info(f"Manual refresh requested for {service_path} by user '{username}'...")
    try:
        # Trigger the health check (which also updates tools if healthy)
        await perform_single_health_check(service_path)
        # --- Regenerate Nginx config after manual refresh --- START
        # The health check itself might trigger regeneration, but do it explicitly
        # here too to ensure it happens after the refresh attempt completes.
        logger.info(f"Regenerating Nginx config after manual refresh for {service_path}...")
        regenerate_nginx_config()
        # --- Regenerate Nginx config after manual refresh --- END
    except Exception as e:
        # Catch potential errors during the check itself
        logger.error(f"ERROR during manual refresh check for {service_path}: {e}")
        # Update status to reflect the error
        error_status = f"error: refresh execution failed ({type(e).__name__})"
        SERVER_HEALTH_STATUS[service_path] = error_status
        SERVER_LAST_CHECK_TIME[service_path] = datetime.now(timezone.utc)
        # Still broadcast the error state
        await broadcast_single_service_update(service_path)
        # --- Regenerate Nginx config even after refresh failure --- START
        # Ensure Nginx reflects the error state if it was previously healthy
        logger.info(f"Regenerating Nginx config after manual refresh failed for {service_path}...")
        regenerate_nginx_config()
        # --- Regenerate Nginx config even after refresh failure --- END
        # Return error response
        raise HTTPException(status_code=500, detail=f"Refresh check failed: {e}")

    # Check completed, broadcast the latest status
    await broadcast_single_service_update(service_path)

    # Return the latest status from global state
    final_status = SERVER_HEALTH_STATUS.get(service_path, "unknown")
    final_last_checked_dt = SERVER_LAST_CHECK_TIME.get(service_path)
    final_last_checked_iso = final_last_checked_dt.isoformat() if final_last_checked_dt else None
    final_num_tools = REGISTERED_SERVERS.get(service_path, {}).get("num_tools", 0)

    return {
        "service_path": service_path,
        "status": final_status,
        "last_checked_iso": final_last_checked_iso,
        "num_tools": final_num_tools
    }
# --- Refresh Endpoint --- END


# --- Add Edit Routes ---

@app.get("/edit/{service_path:path}", response_class=HTMLResponse)
async def edit_server_form(
    request: Request, 
    service_path: str, 
    username: Annotated[str, Depends(get_current_user)] # Require login
):
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    server_info = REGISTERED_SERVERS.get(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not found")
    
    return templates.TemplateResponse(
        "edit_server.html", 
        {"request": request, "server": server_info, "username": username}
    )

@app.post("/edit/{service_path:path}")
async def edit_server_submit(
    service_path: str, 
    # Required Form fields
    name: Annotated[str, Form()], 
    proxy_pass_url: Annotated[str, Form()], 
    # Dependency
    username: Annotated[str, Depends(get_current_user)], 
    # Optional Form fields
    description: Annotated[str, Form()] = "", 
    tags: Annotated[str, Form()] = "", 
    num_tools: Annotated[int, Form()] = 0, 
    num_stars: Annotated[int, Form()] = 0, 
    is_python: Annotated[bool | None, Form()] = False,  
    license_str: Annotated[str, Form(alias="license")] = "N/A", 
):
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Check if the server exists
    if service_path not in REGISTERED_SERVERS:
        raise HTTPException(status_code=404, detail="Service path not found")

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]

    # Prepare updated server data (keeping original path)
    updated_server_entry = {
        "server_name": name,
        "description": description,
        "path": service_path, # Keep original path
        "proxy_pass_url": proxy_pass_url,
        "tags": tag_list,
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": bool(is_python), # Convert checkbox value
        "license": license_str,
    }

    # Save updated data to file
    success = save_server_to_file(updated_server_entry)
    if not success:
        # Optionally render form again with an error message
        raise HTTPException(status_code=500, detail="Failed to save updated server data")

    # Update in-memory registry
    REGISTERED_SERVERS[service_path] = updated_server_entry

    # Regenerate Nginx config as proxy_pass_url might have changed
    if not regenerate_nginx_config():
        logger.error("ERROR: Failed to update Nginx configuration after edit.")
        # Consider how to notify user - maybe flash message system needed
        
    # --- Update FAISS Index --- START
    logger.info(f"Updating service '{service_path}' in FAISS index after edit.")
    if embedding_model and faiss_index is not None:
        await add_or_update_service_in_faiss(service_path, updated_server_entry)
        logger.info(f"Service '{service_path}' updated in FAISS index.")
    else:
        logger.warning(f"Skipped FAISS update for '{service_path}' post-edit: model or index not ready.")
    # --- Update FAISS Index --- END

    logger.info(f"Server '{name}' ({service_path}) updated by user '{username}'")

    # Redirect back to the main page
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# --- Helper function to broadcast single service update --- START
async def broadcast_single_service_update(service_path: str):
    """Sends the current status, tool count, and last check time for a specific service."""
    global active_connections, SERVER_HEALTH_STATUS, SERVER_LAST_CHECK_TIME, REGISTERED_SERVERS

    if not active_connections:
        return # No clients connected

    status = SERVER_HEALTH_STATUS.get(service_path, "unknown")
    last_checked_dt = SERVER_LAST_CHECK_TIME.get(service_path)
    last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
    num_tools = REGISTERED_SERVERS.get(service_path, {}).get("num_tools", 0)

    update_data = {
        service_path: {
            "status": status,
            "last_checked_iso": last_checked_iso,
            "num_tools": num_tools
        }
    }
    message = json.dumps(update_data)
    logger.info(f"--- BROADCAST SINGLE: Sending update for {service_path}: {message}")

    # Use the same concurrent sending logic as in toggle
    disconnected_clients = set()
    current_connections = list(active_connections) # Copy to iterate safely
    send_tasks = []
    for conn in current_connections:
        send_tasks.append((conn, conn.send_text(message)))

    results = await asyncio.gather(*(task for _, task in send_tasks), return_exceptions=True)

    for i, result in enumerate(results):
        conn, _ = send_tasks[i]
        if isinstance(result, Exception):
            logger.warning(f"Error sending single update to WebSocket client {conn.client}: {result}. Marking for removal.")
            disconnected_clients.add(conn)
    if disconnected_clients:
        logger.info(f"Removing {len(disconnected_clients)} disconnected clients after single update broadcast.")
        for conn in disconnected_clients:
            if conn in active_connections:
                active_connections.remove(conn)
# --- Helper function to broadcast single service update --- END


# --- WebSocket Endpoint ---
@app.websocket("/ws/health_status")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket client connected: {websocket.client}")
    try:
        # --- Send initial status upon connection (Formatted) --- START
        initial_data_to_send = {}
        for path, status in SERVER_HEALTH_STATUS.items():
            last_checked_dt = SERVER_LAST_CHECK_TIME.get(path)
            # Send ISO string or None
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            # Get the current tool count from REGISTERED_SERVERS
            num_tools = REGISTERED_SERVERS.get(path, {}).get("num_tools", 0) # Default to 0 if not found

            initial_data_to_send[path] = {
                "status": status,
                "last_checked_iso": last_checked_iso,
                "num_tools": num_tools # --- Add num_tools --- START
            }
            # --- Add num_tools --- END
        await websocket.send_text(json.dumps(initial_data_to_send))
        # --- Send initial status upon connection (Formatted) --- END

        # Keep connection open, handle potential disconnects
        while True:
            # We don't expect messages from client in this case, just keep alive
            await websocket.receive_text() # This will raise WebSocketDisconnect if client closes
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {websocket.client}")
    except Exception as e:
        logger.error(f"WebSocket error for {websocket.client}: {e}")
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)
            logger.info(f"WebSocket connection removed: {websocket.client}")


# --- Run (for local testing) ---
# Use: uvicorn registry.main:app --reload --host 0.0.0.0 --port 7860 --root-path /home/ubuntu/mcp-gateway
# (Running from parent dir)

# If running directly (python registry/main.py):
# if __name__ == "__main__":
#     import uvicorn
#     # Running this way makes relative paths tricky, better to use uvicorn command from parent
#     uvicorn.run(app, host="0.0.0.0", port=7860)
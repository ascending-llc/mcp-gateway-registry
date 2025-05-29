#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# Get the absolute path of the directory where this script is run from
SCRIPT_DIR="$(pwd)"
VENV_DIR="/app/.venv"
REGISTRY_ENV_FILE="/app/registry/.env"
FININFO_ENV_FILE="/app/servers/fininfo/.env"
REGISTRY_ENV_TEMPLATE="/app/registry/.env.template"
EMBEDDINGS_MODEL_NAME="all-MiniLM-L6-v2"
EMBEDDINGS_MODEL_DIMENSIONS=384
FININFO_ENV_TEMPLATE="/app/servers/fininfo/.env.template"
NGINX_CONF_SRC="/app/docker/nginx_rev_proxy.conf"
NGINX_CONF_DEST="/etc/nginx/conf.d/nginx_rev_proxy.conf"
SSL_CERT_DIR="/etc/ssl/certs"
SSL_KEY_DIR="/etc/ssl/private"
SSL_CERT_PATH="$SSL_CERT_DIR/fullchain.pem"
SSL_KEY_PATH="$SSL_KEY_DIR/privkey.pem"

# --- Helper Functions ---
generate_secret_key() {
  python -c 'import secrets; print(secrets.token_hex(32))'
}

# --- Environment Variable Setup ---

# 1. Registry .env
echo "Setting up Registry environment ($REGISTRY_ENV_FILE)..."
# Use provided values or defaults/generated ones
SECRET_KEY_VALUE=${SECRET_KEY:-$(generate_secret_key)}
ADMIN_USER_VALUE=${ADMIN_USER:-admin}

# Check if ADMIN_PASSWORD is set
if [ -z "$ADMIN_PASSWORD" ]; then
  echo "ERROR: ADMIN_PASSWORD environment variable is not set."
  echo "Please set ADMIN_PASSWORD to a secure value before running the container."
  exit 1
fi

ADMIN_PASSWORD_VALUE=${ADMIN_PASSWORD}

# Create .env file from template structure, substituting values
echo "SECRET_KEY=${SECRET_KEY_VALUE}" > "$REGISTRY_ENV_FILE"
echo "ADMIN_USER=${ADMIN_USER_VALUE}" >> "$REGISTRY_ENV_FILE"
echo "ADMIN_PASSWORD=${ADMIN_PASSWORD_VALUE}" >> "$REGISTRY_ENV_FILE"
echo "Registry .env created."
cat "$REGISTRY_ENV_FILE" # Print for verification

# 2. Fininfo Server .env
echo "Setting up Fininfo server environment ($FININFO_ENV_FILE)..."
# Use provided POLYGON_API_KEY or leave it empty (server handles missing key)
POLYGON_API_KEY_VALUE=${POLYGON_API_KEY:-}

# Create .env file from template structure
echo "POLYGON_API_KEY=${POLYGON_API_KEY_VALUE}" > "$FININFO_ENV_FILE"
echo "Fininfo .env created."
cat "$FININFO_ENV_FILE" # Print for verification

# --- Python Environment Setup ---
echo "Checking for Python virtual environment..."
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Setting up Python environment..."
  
  # Install uv if not already installed
  if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    pip install uv
  fi
  
  # Create virtual environment
  echo "Creating virtual environment..."
  uv venv "$VENV_DIR" --python 3.12
  
  # Install dependencies
  echo "Installing Python dependencies..."
  source "$VENV_DIR/bin/activate"
  uv pip install \
    "fastapi>=0.115.12" \
    "itsdangerous>=2.2.0" \
    "jinja2>=3.1.6" \
    "mcp>=1.6.0" \
    "pydantic>=2.11.3" \
    "httpx>=0.27.0" \
    "python-dotenv>=1.1.0" \
    "python-multipart>=0.0.20" \
    "uvicorn[standard]>=0.34.2" \
    "faiss-cpu>=1.7.4" \
    "sentence-transformers>=2.2.2" \
    "websockets>=15.0.1" \
    "scikit-learn>=1.3.0" \
    "torch>=1.6.0" \
    "huggingface-hub[cli,hf_xet]>=0.31.1" \
    "hf_xet>=0.1.0"
  
  # Install the package itself
  uv pip install -e /app
  
  echo "Python environment setup complete."
else
  echo "Python virtual environment already exists, skipping setup."
fi

# --- SSL Certificate Generation ---
echo "Checking for SSL certificates..."
if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
  echo "Generating self-signed SSL certificate for Nginx..."
  # Create directories for SSL certs if they don't exist
  mkdir -p "$SSL_CERT_DIR" "$SSL_KEY_DIR"
  # Generate the certificate and key
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$SSL_KEY_PATH" \
      -out "$SSL_CERT_PATH" \
      -subj "/C=US/ST=State/L=City/O=Organization/OU=OrgUnit/CN=localhost"
  echo "SSL certificate generated."
else
  echo "SSL certificates already exist, skipping generation."
fi

# --- Nginx Configuration ---
echo "Copying custom Nginx configuration..."
cp "$NGINX_CONF_SRC" "$NGINX_CONF_DEST"
echo "Nginx configuration copied to $NGINX_CONF_DEST."

# --- Model Verification ---
EMBEDDINGS_MODEL_DIR="/app/registry/models/$EMBEDDINGS_MODEL_NAME"
echo "Checking for sentence-transformers model..."
if [ ! -d "$EMBEDDINGS_MODEL_DIR" ] || [ -z "$(ls -A "$EMBEDDINGS_MODEL_DIR")" ]; then
  echo "Downloading sentence-transformers model..."
  mkdir -p "$EMBEDDINGS_MODEL_DIR"
  source "$VENV_DIR/bin/activate"
  
  # Ensure CA certificates are installed for SSL verification
  echo "Ensuring CA certificates are installed..."
  apt-get update && apt-get install -y ca-certificates && update-ca-certificates
  
  # Try standard download method first (more reliable)
  echo "Downloading model using standard method..."
  if huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet; then
    echo "Model downloaded successfully using standard method."
  else
    echo "Standard download failed, trying alternative methods..."
    
    # Try with Xet support
    echo "Installing Xet support packages..."
    uv pip install "huggingface-hub[hf_xet]" "hf_xet>=0.1.0" --quiet
    
    # Try with Xet but disable SSL verification if needed
    if ! huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet; then
      echo "Trying download with SSL verification disabled..."
      # Set environment variables to disable SSL verification as a last resort
      export CURL_CA_BUNDLE=""
      export SSL_CERT_FILE=""
      huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet
    fi
  fi
  
  echo "Model downloaded to $EMBEDDINGS_MODEL_DIR"
else
  echo "Model already exists at $EMBEDDINGS_MODEL_DIR, skipping download."
fi

# --- Start Background Services ---
export EMBEDDINGS_MODEL_NAME=$EMBEDDINGS_MODEL_NAME
export EMBEDDINGS_MODEL_DIMENSIONS=$EMBEDDINGS_MODEL_DIMENSIONS 

# 1. Start Example MCP Servers
echo "Starting example MCP servers in the background..."
cd /app
./start_all_servers.sh &
echo "MCP servers start command issued."
# Give servers a moment to initialize
sleep 5

# 2. Start MCP Registry
echo "Starting MCP Registry in the background..."
# Navigate to the registry directory to ensure relative paths work
cd /app/registry
# Use uv run to start uvicorn, ensuring it uses the correct environment
# Run on 0.0.0.0 to be accessible within the container network
# Use port 7860 as configured in nginx proxy_pass
source "$SCRIPT_DIR/.venv/bin/activate"
cd /app/registry && uvicorn main:app --host 0.0.0.0 --port 7860 &
echo "MCP Registry start command issued."
# Give registry a moment to initialize and generate initial nginx config
sleep 10

# --- Start Nginx in Background ---
echo "Starting Nginx in the background..."
# Start nginx normally, it will daemonize by default
nginx

echo "Nginx started. Keeping container alive..."
# Keep the container running indefinitely
tail -f /dev/null

echo "Entrypoint script finished." # This line will likely not be reached unless tail fails
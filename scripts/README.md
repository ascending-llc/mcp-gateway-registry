# Scripts Directory

This directory contains utility scripts for the MCP Gateway and Registry project.

## Atlassian OAuth Setup Scripts

### setup-atlassian-env.sh

Sets up environment variables and runs the Atlassian OAuth setup process.

**Prerequisites:**
- Set the following environment variables before running:
  - `ATLASSIAN_OAUTH_CLIENT_ID` - Your Atlassian OAuth client ID
  - `ATLASSIAN_OAUTH_CLIENT_SECRET` - Your Atlassian OAuth client secret

**Usage:**
```bash
# Set environment variables
export ATLASSIAN_OAUTH_CLIENT_ID="your_client_id_here"
export ATLASSIAN_OAUTH_CLIENT_SECRET="your_client_secret_here"

# Run the setup script
./scripts/setup-atlassian-env.sh
```

**What it does:**
1. Validates required environment variables are set
2. Sets additional OAuth configuration (redirect URI, scopes)
3. Runs the Atlassian MCP OAuth setup container
4. Saves OAuth tokens to `~/.mcp-atlassian/`

### run-oauth-setup.sh

Alternative OAuth setup script (if available).

## Security Note

All sensitive information must be provided through environment variables to maintain security.
#!/bin/bash

# Atlassian OAuth Environment Variables Setup Script
# This script sets up the required environment variables for the Atlassian MCP server

echo "Setting up Atlassian OAuth environment variables..."

# Check if required environment variables are set
if [ -z "$ATLASSIAN_OAUTH_CLIENT_ID" ] || [ -z "$ATLASSIAN_OAUTH_CLIENT_SECRET" ]; then
    echo ""
    echo "ERROR: Required environment variables are not set!"
    echo ""
    echo "Please set the following environment variables before running this script:"
    echo "  ATLASSIAN_OAUTH_CLIENT_ID     - Your Atlassian OAuth client ID"
    echo "  ATLASSIAN_OAUTH_CLIENT_SECRET - Your Atlassian OAuth client secret"
    echo ""
    echo "You can set them by running:"
    echo "  export ATLASSIAN_OAUTH_CLIENT_ID=\"your_client_id_here\""
    echo "  export ATLASSIAN_OAUTH_CLIENT_SECRET=\"your_client_secret_here\""
    echo ""
    echo "Or create a .env file and source it before running this script."
    echo ""
    exit 1
fi

# Validate that the environment variables are not empty
if [ -z "${ATLASSIAN_OAUTH_CLIENT_ID// }" ] || [ -z "${ATLASSIAN_OAUTH_CLIENT_SECRET// }" ]; then
    echo ""
    echo "ERROR: Environment variables cannot be empty!"
    echo ""
    exit 1
fi
export ATLASSIAN_OAUTH_REDIRECT_URI="http://localhost:8080/callback"
export ATLASSIAN_OAUTH_SCOPE="offline_access write:confluence-content read:confluence-space.summary write:confluence-space write:confluence-file read:confluence-props write:confluence-props manage:confluence-configuration read:confluence-content.all read:confluence-content.summary search:confluence read:confluence-content.permission read:confluence-user read:confluence-groups write:confluence-groups readonly:content.attachment:confluence read:jira-work manage:jira-project manage:jira-configuration read:jira-user write:jira-work manage:jira-webhook manage:jira-data-provider read:servicedesk-request manage:servicedesk-customer write:servicedesk-request read:servicemanagement-insight-objects read:me read:account report:personal-data write:component:compass read:scorecard:compass write:scorecard:compass read:component:compass read:event:compass write:event:compass read:metric:compass write:metric:compass read:backup:brie write:backup:brie read:restore:brie write:restore:brie read:account:brie write:storage:brie"

echo "Environment variables validated successfully!"
echo ""
echo "Using configured variables:"
echo "  ATLASSIAN_OAUTH_CLIENT_ID: $ATLASSIAN_OAUTH_CLIENT_ID"
echo "  ATLASSIAN_OAUTH_CLIENT_SECRET: ${ATLASSIAN_OAUTH_CLIENT_SECRET:0:20}... (truncated for security)"
echo "  ATLASSIAN_OAUTH_REDIRECT_URI: $ATLASSIAN_OAUTH_REDIRECT_URI"
echo "  ATLASSIAN_OAUTH_SCOPE: ${ATLASSIAN_OAUTH_SCOPE:0:50}... (truncated for display)"
echo ""
echo "Now running the OAuth setup container..."
echo ""

# Run the OAuth setup container
docker run --rm -i \
  -p 8080:8080 \
  -v "${HOME}/.mcp-atlassian:/home/app/.mcp-atlassian" \
  -e "ATLASSIAN_OAUTH_CLIENT_ID=${ATLASSIAN_OAUTH_CLIENT_ID}" \
  -e "ATLASSIAN_OAUTH_CLIENT_SECRET=${ATLASSIAN_OAUTH_CLIENT_SECRET}" \
  -e "ATLASSIAN_OAUTH_REDIRECT_URI=${ATLASSIAN_OAUTH_REDIRECT_URI}" \
  -e "ATLASSIAN_OAUTH_SCOPE=${ATLASSIAN_OAUTH_SCOPE}" \
  ghcr.io/sooperset/mcp-atlassian:latest --oauth-setup -v

echo ""
echo "OAuth setup completed!"
echo "You can now use the configured credentials with the Atlassian MCP server."

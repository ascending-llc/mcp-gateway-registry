#!/bin/bash

echo "Running Atlassian OAuth Setup..."
echo "This will start a temporary container on port 8080 for OAuth configuration."
echo ""

# Ensure the directory has proper permissions
sudo chown -R ubuntu:ubuntu ~/.mcp-atlassian/
sudo chmod 755 ~/.mcp-atlassian/

echo "Starting OAuth setup container..."
echo "Visit http://localhost:8080 in your browser to complete the OAuth setup."
echo ""

./setup-atlassian-env.sh

echo ""
echo "OAuth setup completed. Checking for created files..."
ls -la ~/.mcp-atlassian/
echo ""

# Update .env files with Atlassian OAuth tokens
echo "Updating .env files with Atlassian OAuth tokens..."
python3 <<'EOF'
import json
import os
import glob

# Find the OAuth JSON file
oauth_files = glob.glob('/home/ubuntu/.mcp-atlassian/oauth-*.json')
if not oauth_files:
    print("❌ No OAuth JSON file found in ~/.mcp-atlassian/")
    exit(1)

oauth_file = oauth_files[0]
print(f"📖 Reading OAuth token from: {oauth_file}")

try:
    # Read the OAuth data
    with open(oauth_file, 'r') as f:
        oauth_data = json.load(f)

    access_token = oauth_data.get('access_token', '')
    cloud_id = oauth_data.get('cloud_id', '')

    if not access_token:
        print("❌ No access_token found in OAuth file")
        exit(1)

    print(f"✅ Found access_token (first 50 chars): {access_token[:50]}...")
    print(f"✅ Found cloud_id: {cloud_id}")

    # Update function to add/update tokens in .env files
    def update_env_file(file_path, updates):
        """Update or add environment variables in a .env file"""
        lines = []
        updated_vars = set()

        # Read existing file if it exists
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    # Check if this line sets one of our variables
                    var_updated = False
                    for var_name in updates:
                        if line.startswith(f'{var_name}='):
                            lines.append(f'{var_name}={updates[var_name]}\n')
                            updated_vars.add(var_name)
                            var_updated = True
                            break

                    if not var_updated:
                        lines.append(line)

        # Add any variables that weren't already in the file
        for var_name, var_value in updates.items():
            if var_name not in updated_vars:
                # Ensure there's a newline before adding new vars
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
                lines.append(f'{var_name}={var_value}\n')

        # Write the updated file
        with open(file_path, 'w') as f:
            f.writelines(lines)

        print(f"✅ Updated {file_path}")

    # Prepare the updates
    env_updates = {
        'ATLASSIAN_AUTH_TOKEN': access_token,
        'ATLASSIAN_CLOUD_ID': cloud_id
    }

    # Update both .env.agent and .env.user files
    agent_env = '/home/ubuntu/repos/mcp-gateway-registry/agents/.env.agent'
    user_env = '/home/ubuntu/repos/mcp-gateway-registry/agents/.env.user'

    update_env_file(agent_env, env_updates)
    update_env_file(user_env, env_updates)

    print("\n✅ Successfully updated both .env files with Atlassian OAuth tokens!")
    print("   - ATLASSIAN_AUTH_TOKEN: Set")
    print(f"   - ATLASSIAN_CLOUD_ID: {cloud_id}")

except Exception as e:
    print(f"❌ Error processing OAuth file: {e}")
    exit(1)
EOF

echo ""
echo "If you see oauth-*.json files above, the setup was successful."

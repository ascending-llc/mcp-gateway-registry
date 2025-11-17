# MCP Gateway & Registry v1.0.4

**Release Date:** October 14, 2025

We're excited to announce v1.0.4 of the MCP Gateway & Registry - featuring major enhancements for Anthropic MCP Registry integration, environment variable management, and improved documentation.

## What's New

### Anthropic MCP Registry Integration

Seamlessly integrate with Anthropic's official MCP Registry to import and access curated MCP servers through your gateway!

**Import Servers from Anthropic Registry** (#171)
- **One-Command Import** - Import curated MCP servers with a single command
- **Automatic Configuration** - Server metadata, authentication, and tags automatically configured
- **Environment Variable Substitution** - API keys and credentials automatically substituted from `.env` file
- **Bulk Import Support** - Import multiple servers from a list file
- **Unified Access** - Access imported servers through your gateway with centralized authentication

**Anthropic Registry REST API v0 Compatibility** (#178)
- **Full API Compatibility** - Complete support for Anthropic's Registry REST API v0 specification
- **Server Discovery** - List available servers programmatically with JWT authentication
- **Version Information** - Retrieve server versions and compatibility details
- **Programmatic Access** - Point your Anthropic API clients to this registry

**Documentation:**
- [Anthropic Registry Import Guide](docs/anthropic-registry-import.md) - Comprehensive guide for importing servers
- [Registry REST API v0 Documentation](docs/anthropic_registry_api.md) - API reference and examples

**Example Usage:**
```bash
# Import a single server
./cli/import_from_anthropic_registry.sh ai.smithery/smithery-ai-github

# Import from a curated list
./cli/import_from_anthropic_registry.sh --import-list cli/import_server_list.txt

# List available servers via API
curl https://your-gateway/v0/servers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Enhanced Authentication & Environment Management

**Automatic Environment Variable Substitution** (#181)
- **Smart Header Processing** - Authentication headers automatically populated from environment variables
- **Import-Time Substitution** - Environment variables substituted during server import, not at runtime
- **Simplified Configuration** - No need to pass environment variables to Docker containers
- **Auto-Load .env File** - Import script automatically sources `.env` file

**Before:**
```bash
# Manual environment variable management
source .env
export SMITHERY_API_KEY
./cli/import_from_anthropic_registry.sh server-name
```

**After:**
```bash
# Automatic - just run the import
./cli/import_from_anthropic_registry.sh server-name
```

### Bug Fixes

**UI Improvements**
- **Fixed proxy_pass_url Display** - UI now correctly shows upstream URLs for imported servers
- **Added Missing Field** - `/servers` API endpoint now includes `proxy_pass_url` in response

**Model Download Optimization** (#176)
- **Removed Redundant Download** - Eliminated model download from registry entrypoint
- **Faster Startup** - Registry container starts faster with pre-downloaded models
- **Better User Experience** - Model download now handled by setup scripts

### Documentation Improvements

**New Documentation**
- **Anthropic Registry Import Guide** - Complete guide for importing servers from Anthropic's registry
- **REST API v0 Documentation** - Full API reference for Anthropic registry compatibility
- **Enhanced README** - More concise with better organization and navigation

**README Updates**
- Condensed "What's New" section (reduced from 14 to 6 key items)
- Simplified deployment and infrastructure details
- Added Anthropic documentation links to docs table
- Removed verbose sections for better readability

**macOS Setup Guide Updates** (#177)
- Updated installation instructions for macOS users
- Platform-specific optimizations and troubleshooting

### Roadmap Updates

**Completed Features**
- **#171** - Import Servers from Anthropic MCP Registry
- **#37** - Multi-Level Registry Support (via Anthropic integration)

These features enable federated registry support and seamless integration with the broader MCP ecosystem.

## Breaking Changes

None - this release is fully backward compatible with v1.0.3.

## Upgrade Instructions

### For Existing Installations

1. **Pull the latest changes:**
```bash
cd mcp-gateway-registry
git pull origin main
```

2. **Update environment configuration:**
Add any new API keys to your `.env` file:
```bash
# Example: Smithery API key for imported servers
SMITHERY_API_KEY=your-api-key-here
```

3. **Restart services:**
```bash
./build_and_run.sh
```

### For Pre-built Image Users

```bash
cd mcp-gateway-registry
git pull origin main
./build_and_run.sh --prebuilt
```

## Migration Notes

### Importing Servers

If you want to import servers from Anthropic's registry:

1. **Add required API keys to `.env`:**
```bash
# Add authentication keys for services you want to import
SMITHERY_API_KEY=your-key
OTHER_SERVICE_KEY=your-key
```

2. **Create import list:**
```bash
# Create cli/import_server_list.txt with desired servers
echo "ai.smithery/smithery-ai-github" >> cli/import_server_list.txt
echo "io.github.jgador/websharp" >> cli/import_server_list.txt
```

3. **Run import:**
```bash
./cli/import_from_anthropic_registry.sh --import-list cli/import_server_list.txt
```

## Known Issues

- Authentication keys must be valid for successful server imports
- Some Smithery servers may require specific API key permissions
- Imported servers with invalid credentials will show as "auth-expired" in health checks

## Contributors

Thank you to all contributors who made this release possible!

- Environment variable substitution and import functionality
- Anthropic Registry API compatibility
- Documentation improvements
- Bug fixes and UI enhancements

## What's Next

Looking ahead to v1.0.5:

- **#170** - Separate Gateway and Registry Containers (In Progress)
- **#132** - MCP Configuration Generator in Registry UI
- **#129** - Virtual MCP Server Support with Dynamic Tool Aggregation
- **#128** - Microsoft Entra ID (Azure AD) Authentication Provider

For the complete roadmap, see [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues).

## Resources

- [Complete Setup Guide](docs/complete-setup-guide.md)
- [Anthropic Registry Import Guide](docs/anthropic-registry-import.md)
- [Anthropic Registry REST API Documentation](docs/anthropic_registry_api.md)
- [Service Management Guide](docs/service-management.md)
- [Observability Guide](docs/OBSERVABILITY.md)

## Support

- [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)
- [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions)
- [Documentation](https://github.com/agentic-community/mcp-gateway-registry/tree/main/docs)

---

**Full Changelog:** [v1.0.3...v1.0.4](https://github.com/agentic-community/mcp-gateway-registry/compare/v1.0.3...v1.0.4)

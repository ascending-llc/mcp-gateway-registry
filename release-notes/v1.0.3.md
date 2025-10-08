# MCP Gateway & Registry v1.0.3

**Release Date:** October 8, 2025

We're excited to announce v1.0.3 of the MCP Gateway & Registry - the enterprise-ready platform that centralizes access to AI development tools using the Model Context Protocol (MCP).

## What's New

### Amazon Bedrock AgentCore Gateway Integration

Seamlessly integrate Amazon Bedrock AgentCore Gateways with the MCP Gateway Registry! This major enhancement brings enterprise-grade AI assistant capabilities to your MCP infrastructure.

**Key Features:**
- **Dual Authentication Flow** - Keycloak ingress authentication for gateway access + Cognito egress authentication for AgentCore
- **Passthrough Token Mode** - AgentCore tokens bypass gateway validation for direct authentication with AWS Cognito
- **Complete MCP Protocol Support** - Full session initialization, tool discovery, and tool execution
- **Production-Ready Examples** - Customer support assistant with warranty lookup and customer profile tools

**Documentation:** [Amazon Bedrock AgentCore Integration Guide](docs/agentcore.md)

**Use Cases:**
- Deploy customer support assistants with knowledge base integration
- Access AWS Lambda functions through managed MCP endpoints
- Build AI agents with enterprise authentication and audit trails

### Pre-built Docker Images - Deploy in Under 10 Minutes

Get running instantly with our pre-built Docker images! No compilation required - just download and run.

**Benefits:**
- Instant deployment with `./build_and_run.sh --prebuilt`
- Faster updates and rollbacks
- Support for both EC2 and macOS deployments
- All components pre-compiled and optimized

**Documentation:**
- [Quick Start Guide](README.md#option-a-pre-built-images-instant-setup)
- [macOS Setup Guide](docs/macos-setup-guide.md)
- [Pre-built Images Documentation](docs/prebuilt-images.md)

### Keycloak Identity Provider Integration

Enterprise-grade authentication with complete audit trails and group-based authorization.

**Features:**
- Individual AI agent identity management
- Group-based access control with fine-grained permissions
- Service account provisioning for automation
- Production-ready OAuth 2.0 flows (M2M, 2LO, 3LO)
- Complete audit trail for compliance (GDPR, SOX)

**Documentation:** [Keycloak Integration Guide](docs/keycloak-integration.md)

### Real-Time Metrics & Observability

Comprehensive monitoring and observability platform built on industry-standard tools.

**Components:**
- **Grafana Dashboards** - Pre-built dashboards for server health, tool usage, and authentication
- **SQLite Storage** - Efficient metrics storage with OTEL integration
- **Real-Time Monitoring** - Track performance, errors, and usage patterns
- **Custom Metrics** - Emit application-specific metrics from any component

**Access:** http://localhost:3000 (Grafana) | http://localhost:7860 (Registry UI)

**Documentation:** [Observability Guide](docs/OBSERVABILITY.md)

### Service & User Management Utilities

Comprehensive CLI tools for complete lifecycle management of MCP servers and users.

**Capabilities:**
- Server registration and health validation
- User provisioning with Keycloak integration
- Group-based access control configuration
- Automated testing and verification
- Complete workflow examples

**CLI Tools:**
- `service_mgmt.sh` - Server lifecycle management
- User management utilities - Group and scope configuration
- Health check automation

**Documentation:** [Service Management Guide](docs/service-management.md)

## Enhanced Features

### Tag-Based Tool Filtering
Enhanced `intelligent_tool_finder` now supports hybrid search:
- Semantic search for natural language queries
- Tag-based filtering for categorical discovery
- Combined search modes for precise tool selection

### Three-Legged OAuth (3LO) Support
Integrate external services with user consent flows:
- Atlassian (Jira, Confluence)
- Google Workspace
- GitHub
- Custom OAuth providers

### JWT Token Vending Service
Self-service token generation for automation:
- Service account tokens
- Time-limited access tokens
- Automated credential rotation

### Automated Token Refresh Service
Background token refresh maintains continuous authentication:
- Automatic token renewal before expiration
- Seamless credential management
- Zero-downtime authentication

## Improvements

### Installation & Deployment
- Eliminated sudo requirements - uses `${HOME}` instead of `/opt`
- Pre-built Docker images for instant deployment
- Improved EC2 and macOS compatibility
- Remote desktop setup guide for easier access

### Authentication & Security
- Dual authentication support (ingress + egress)
- Passthrough token mode for external IdPs
- Enhanced audit trails and compliance features
- Fine-grained access control (FGAC) at server and tool levels

### Developer Experience
- Comprehensive documentation with examples
- CLI tools for automation
- Complete workflow examples
- Modern React frontend with TypeScript

### Observability
- Real-time Grafana dashboards
- OTEL-compatible metrics
- Performance tracking
- Usage analytics

## Bug Fixes

- Fixed URL formatting for bedrock-agentcore services
- Improved token validation and refresh flows
- Enhanced error messages and troubleshooting guides
- Corrected documentation links and anchors

## Documentation Updates

- **New:** [Amazon Bedrock AgentCore Integration Guide](docs/agentcore.md)
- **Updated:** [Service Management Guide](docs/service-management.md)
- **Updated:** [Keycloak Integration Guide](docs/keycloak-integration.md)
- **Updated:** [Observability Guide](docs/OBSERVABILITY.md)
- **New:** [macOS Setup Guide](docs/macos-setup-guide.md)
- **New:** [Remote Desktop Setup Guide](docs/remote-desktop-setup.md)

## Quick Start

### Option A: Pre-built Images (Recommended)

```bash
# Clone and setup
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry
cp .env.example .env

# Configure environment
export DOCKERHUB_ORG=mcpgateway

# Deploy with pre-built images
./build_and_run.sh --prebuilt
```

### Option B: Build from Source

```bash
# Clone and setup
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# Build and run
./build_and_run.sh
```

**Next Steps:**
1. Initialize Keycloak: Follow [Initial Environment Configuration](docs/complete-setup-guide.md#initialize-keycloak-configuration)
2. Create your first AI agent: [Create Your First AI Agent Account](docs/complete-setup-guide.md#create-your-first-ai-agent-account)
3. Access the registry UI: http://localhost:7860
4. Monitor with Grafana: http://localhost:3000

## Demo Videos

- [Full End-to-End Functionality](https://github.com/user-attachments/assets/5ffd8e81-8885-4412-a4d4-3339bbdba4fb)
- [OAuth 3-Legged Authentication](https://github.com/user-attachments/assets/3c3a570b-29e6-4dd3-b213-4175884396cc)
- [Dynamic Tool Discovery](https://github.com/user-attachments/assets/cee25b31-61e4-4089-918c-c3757f84518c)

## What's Included

- **MCP Gateway** - Central gateway for all MCP traffic
- **Registry Service** - Server and tool catalog with discovery
- **Auth Server** - OAuth 2.0 authentication with Keycloak/Cognito
- **Frontend UI** - Modern React interface for management
- **Metrics Service** - OTEL-compatible observability
- **CLI Tools** - Complete automation suite

## System Requirements

- Docker and Docker Compose
- Python 3.11+ (for development)
- 4GB RAM minimum (8GB recommended)
- EC2 instance or macOS system

## Community & Support

- **Documentation:** [docs/](docs/)
- **Issues:** [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)
- **Discussions:** [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Completed in This Release

- #160 - Amazon Bedrock AgentCore Gateway integration documentation
- #158 - Eliminate sudo requirements with ${HOME} directory usage
- #111 - Standalone metrics collection service
- #38 - Usage metrics and analytics system
- #120 - CLI tool for MCP server registration and health validation
- #119 - Well-known URL for MCP server discovery
- #18 - Token vending capability
- #5 - Keycloak IdP provider support

## Roadmap

See our [complete roadmap](README.md#roadmap) for upcoming features including:
- Multi-level registry support (federated registries)
- Virtual MCP server support with intelligent routing
- Microsoft Entra ID (Azure AD) authentication
- OpenSearch integration for advanced vector search
- Agent-as-tool dynamic MCP server generation

## License

This project is licensed under the Apache-2.0 License - see the [LICENSE](LICENSE) file for details.

---

**Star this repository if it helps your organization!**

[Get Started](docs/installation.md) | [Documentation](docs/) | [Contribute](CONTRIBUTING.md)

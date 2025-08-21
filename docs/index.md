<div align="center">
<img src="img/mcp_gateway_horizontal_white_logo.png" alt="MCP Gateway Logo" width="100%">

**Enterprise-Ready Gateway for AI Development Tools**

</div>

## Enterprise-Grade MCP Server & Registry

A comprehensive solution for managing, securing, and accessing Model Context Protocol (MCP) servers at scale. Built for enterprises, development teams, and autonomous AI agents.

### 🎬 Demo Videos

| Feature | Demo |
|---------|------|
| **🔐 OAuth Authentication** | [Watch OAuth Setup](https://github.com/agentic-community/mcp-gateway-registry/assets/your-user/demo-oauth.mp4) |
| **🤖 AI Agent Integration** | [Watch AI Agents](https://github.com/agentic-community/mcp-gateway-registry/assets/your-user/demo-ai-agents.mp4) |

### 🔧 MCP Tools in Action

<div align="center">
<img src="img/MCP_tools.gif" alt="MCP Tools Demo" width="800"/>
</div>

*Experience dynamic tool discovery and intelligent MCP server integration in real-time*

---

## Key Features

### 🏢 Enterprise-Ready Architecture
- **Reverse Proxy**: Centralized access point for all MCP servers
- **Service Discovery**: Automatic registration and health monitoring
- **Load Balancing**: Intelligent request distribution across server instances
- **High Availability**: Production-ready deployment patterns

### 🔐 Advanced Security & Authentication
- **OAuth 2.0 Integration**: Amazon Cognito, Google, GitHub, and custom providers
- **Fine-Grained Access Control**: Role-based permissions with scope management
- **JWT Token Vending**: Secure token generation and validation
- **Audit Logging**: Comprehensive security event tracking

### 🤖 AI Agent Optimization
- **Dynamic Tool Discovery**: Runtime MCP server and tool enumeration
- **Intelligent Tool Finder**: AI-powered tool recommendation and selection
- **Autonomous Access Control**: Context-aware permission management
- **Multi-Agent Coordination**: Shared resource access with conflict resolution

### 🛠️ Developer Experience
- **React Web Interface**: Intuitive server management and monitoring
- **REST API**: Programmatic registry management and integration
- **AI Coding Assistant Integration**: VS Code, Cursor, Claude Code support
- **Real-Time Monitoring**: Live server health and performance metrics

---

## Quick Start

!!! tip "Prerequisites"
    Before proceeding, ensure you have satisfied all [prerequisites](installation.md#prerequisites) including Docker, AWS account setup, and Amazon Cognito configuration.

Get up and running in 5 minutes with Docker Compose:

```bash
# 1. Clone and setup
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# 2. Configure environment
cp .env.example .env
# Edit .env with your AWS Cognito credentials

# 3. Generate authentication credentials  
./credentials-provider/generate_creds.sh

# 4. Deploy with Docker Compose
docker-compose up -d

# 5. Access the registry
open http://localhost:7860
```

The registry will be available at `http://localhost:7860` with example MCP servers pre-configured.

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph "Client Layer"
        A1[AI Agents]
        A2[Development Tools]
        A3[Web Interface]
    end
    
    subgraph "MCP Gateway & Registry"
        B1[Nginx Reverse Proxy]
        B2[OAuth Authentication]
        B3[Registry Service]
        B4[Access Control Engine]
    end
    
    subgraph "MCP Server Ecosystem"
        C1[Atlassian MCP Server]
        C2[Financial Data Server]
        C3[Time & Calendar Server]
        C4[Custom Enterprise Servers]
    end
    
    A1 --> B1
    A2 --> B1
    A3 --> B1
    
    B1 --> B2
    B2 --> B4
    B4 --> B3
    
    B1 --> C1
    B1 --> C2
    B1 --> C3
    B1 --> C4
```

The MCP Gateway & Registry acts as a centralized hub that:

1. **Authenticates** users and AI agents through OAuth providers
2. **Authorizes** access based on fine-grained scopes and permissions
3. **Routes** requests to appropriate MCP servers
4. **Monitors** server health and performance
5. **Discovers** available tools and capabilities dynamically

---

## Use Cases

### 🏢 Enterprise Integration
Transform how both autonomous AI agents and development teams access enterprise systems:

- **Unified Access Point**: Single endpoint for all MCP servers across your organization
- **Enterprise SSO**: Integration with existing identity providers (Cognito, SAML, OIDC)
- **Compliance & Governance**: Comprehensive audit trails and access control policies
- **Scalable Architecture**: Support for hundreds of MCP servers and thousands of concurrent users

### 🤖 AI Agent Workflows
Enable sophisticated AI agent interactions with enterprise systems:

- **Dynamic Tool Discovery**: Agents discover and utilize tools based on current context
- **Intelligent Tool Selection**: AI-powered recommendations for optimal tool usage
- **Multi-Agent Coordination**: Shared access to enterprise resources with conflict resolution
- **Context-Aware Permissions**: Dynamic access control based on agent capabilities and current task

### 👩‍💻 Development Team Productivity
Accelerate development workflows with integrated tooling:

- **IDE Integration**: Native support for VS Code, Cursor, and Claude Code
- **Real-Time Collaboration**: Shared access to development tools and services
- **Environment Management**: Consistent tool access across development, staging, and production
- **API-First Design**: Programmatic access for custom integrations and automation

---

## Documentation

| Getting Started | Authentication & Security | Architecture & Development |
|-----------------|---------------------------|----------------------------|
| [Installation Guide](installation.md)<br/>Complete setup instructions for EC2 and EKS | [Authentication Guide](auth.md)<br/>OAuth and identity provider integration | [AI Coding Assistants Setup](ai-coding-assistants-setup.md)<br/>VS Code, Cursor, Claude Code integration |
| [Quick Start Tutorial](quick-start.md)<br/>Get running in 5 minutes | [Amazon Cognito Setup](cognito.md)<br/>Step-by-step IdP configuration | [API Reference](registry_api.md)<br/>Programmatic registry management |
| [Configuration Reference](configuration.md)<br/>Environment variables and settings | [Fine-Grained Access Control](scopes.md)<br/>Permission management and security | [Dynamic Tool Discovery](dynamic-tool-discovery.md)<br/>Autonomous agent capabilities |
| | | [Production Deployment](installation.md)<br/>Complete setup for production environments |
| | | [Troubleshooting Guide](FAQ.md)<br/>Common issues and solutions |

---

## Community & Support

**Getting Help**
- [FAQ & Troubleshooting](FAQ.md) - Common questions and solutions
- [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues) - Bug reports and feature requests
- [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions) - Community support and ideas

**Resources**
- [Demo Videos](https://github.com/agentic-community/mcp-gateway-registry#demo-videos) - See the platform in action

**Contributing**
- [Contributing Guide](CONTRIBUTING.md) - How to contribute code and documentation
- [Code of Conduct](CODE_OF_CONDUCT.md) - Community guidelines and expectations

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Part of the [Agentic Community](https://github.com/agentic-community) ecosystem - building the future of AI-driven development.*
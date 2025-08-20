<div align="center">
<img src="registry/static/mcp_gateway_horizontal_white_logo.png" alt="MCP Gateway Logo" width="100%">

**Enterprise-Ready Gateway for AI Development Tools**

[![GitHub stars](https://img.shields.io/github/stars/agentic-community/mcp-gateway-registry?style=flat&logo=github)](https://github.com/agentic-community/mcp-gateway-registry/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/agentic-community/mcp-gateway-registry?style=flat&logo=github)](https://github.com/agentic-community/mcp-gateway-registry/network)
[![GitHub issues](https://img.shields.io/github/issues/agentic-community/mcp-gateway-registry?style=flat&logo=github)](https://github.com/agentic-community/mcp-gateway-registry/issues)
[![License](https://img.shields.io/github/license/agentic-community/mcp-gateway-registry?style=flat)](https://github.com/agentic-community/mcp-gateway-registry/blob/main/LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/agentic-community/mcp-gateway-registry?style=flat&logo=github)](https://github.com/agentic-community/mcp-gateway-registry/releases)

[Quick Start](#quick-start) | [Documentation](docs/) | [Enterprise Features](#enterprise-features) | [Community](#community)

</div>

---

## What is MCP Gateway & Registry?

The **MCP Gateway & Registry** is an enterprise-ready platform that centralizes access to AI development tools using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction). Instead of managing hundreds of individual tool configurations across your development teams, provide secure, governed access to curated AI tools through a single platform.

**Transform this chaos:**
```
❌ Each developer configures VS Code, Cursor, Claude Code individually
❌ Scattered API keys and credentials across tools  
❌ No visibility into what tools teams are using
❌ Security risks from unmanaged tool sprawl
```

**Into this organized approach:**
```
✅ Centralized tool catalog with enterprise governance
✅ Single sign-on through your identity provider
✅ Complete audit trail and compliance ready
✅ Consistent developer experience across all AI assistants
```

---

## Core Use Cases

### AI Development Tool Governance
Provide developers with secure access to approved AI development tools while maintaining IT oversight and compliance.

### Enterprise Security & Compliance  
Centralized authentication, fine-grained permissions, and comprehensive audit trails for SOX/GDPR compliance pathways.

### Dynamic Tool Discovery
AI agents can autonomously discover and execute specialized tools beyond their initial capabilities using intelligent semantic search.

### Microservices Integration
Seamlessly integrate with existing enterprise architecture including Amazon Cognito, SAML, and AWS services.

---

## Key Advantages

### **Enterprise-Grade Security**
- OAuth 2.0/3.0 compliance with IdP integration
- Fine-grained access control at tool and method level  
- Zero-trust network architecture
- Complete audit trails for compliance

### **Developer Experience**
- Single configuration works across VS Code, Cursor, Claude Code, Cline
- Dynamic tool discovery with natural language queries
- Instant onboarding for new team members
- Consistent experience across all AI coding assistants

### **Production Ready**
- High availability with multi-AZ deployment
- Container-native (Docker/Kubernetes)
- Real-time health monitoring and alerting
- Horizontal scaling support

### **Extensible & Open**
- Based on open Model Context Protocol standard
- Custom MCP server integration
- API-first design for programmatic management
- Plugin architecture for extensions

---

## Quick Start

Get up and running in 5 minutes with Docker Compose:

```bash
# Clone the repository
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# Configure environment
cp .env.example .env
# Edit .env with your Cognito credentials

# Generate authentication credentials
./credentials-provider/generate_creds.sh

# Deploy with Docker Compose
./build_and_run.sh

# Access the registry
open http://localhost:7860
```

**That's it!** Your enterprise MCP gateway is now running.

➡️ **Next Steps:** [Complete Installation Guide](docs/installation.md) | [Authentication Setup](docs/auth.md) | [AI Assistant Integration](docs/ai-coding-assistants-setup.md)

---

## 🏢 Enterprise Features

### AI Coding Assistants Integration

Transform how your development teams access AI tools with centralized governance:

<table>
<tr>
<td width="50%">
<img src="docs/img/roo.png" alt="Roo Code MCP Configuration" />
<p><em>Enterprise-curated MCP servers accessible through unified gateway</em></p>
</td>
<td width="50%">
<img src="docs/img/roo_agent.png" alt="Roo Code Agent in Action" />
<p><em>AI assistants executing approved enterprise tools with governance</em></p>
</td>
</tr>
</table>

**Supported AI Development Tools:**
- **VS Code MCP Extension** - Microsoft's popular editor with MCP support
- **Roo Code** - AI-powered development assistant with enterprise governance
- **Claude Code** - Anthropic's coding assistant with standardized configurations  
- **Cursor** - AI-first code editor with MCP integration
- **Cline** - Autonomous coding agent compatible with VS Code

**Enterprise Benefits:**
- **Centralized Control** - IT manages approved tools across all teams
- **Secure Authentication** - Enterprise identity integration (Amazon Cognito)
- **Usage Analytics** - Track tool adoption and usage patterns
- **Compliance Ready** - Complete audit trails for enterprise requirements

### Authentication & Authorization

**Multiple Identity Modes:**
- **Machine-to-Machine (M2M)** - For autonomous AI agents
- **Three-Legged OAuth (3LO)** - For external service integration
- **Session-Based** - For web interface access

**Supported Identity Providers:**
- Amazon Cognito (Primary)
- SAML 2.0 
- LDAP/Active Directory

**Fine-Grained Permissions:**
- Tool-level access control
- Method-level restrictions  
- Team-based permissions
- Temporary access grants

### Production Deployment

**Cloud Platforms:**
- **Amazon EC2** - Single instance or auto-scaling groups
- **Amazon EKS** - Kubernetes-native microservices deployment
- **On-Premises** - Private cloud and data center deployment

**High Availability:**
- Multi-AZ deployment with automatic failover
- Health monitoring and alerting
- Rolling updates with zero downtime
- Backup and disaster recovery

---

## What's New

- **Amazon Bedrock AgentCore Integration** - Direct access to AWS services through managed MCP endpoints
- **Three-Legged OAuth (3LO) Support** - External service integration (Atlassian, Google, GitHub)
- **JWT Token Vending Service** - Self-service token generation for automation
- **Modern React Frontend** - Complete UI overhaul with TypeScript and real-time updates
- **Dynamic Tool Discovery** - AI agents autonomously find and execute specialized tools
- **Fine-Grained Access Control** - Granular permissions for servers, methods, and individual tools

[📖 Full Release Notes](docs/changelog.md)

---

## Documentation

### Getting Started
- [Installation Guide](docs/installation.md) - Complete setup instructions for EC2 and EKS
- [Quick Start Tutorial](docs/quick-start.md) - Get running in 5 minutes
- [Configuration Reference](docs/configuration.md) - Environment variables and settings

### Enterprise Setup  
- [Authentication Guide](docs/auth.md) - OAuth, SAML, and identity provider integration
- [Amazon Cognito Setup](docs/cognito.md) - Step-by-step IdP configuration
- [Fine-Grained Access Control](docs/scopes.md) - Permission management and security

### Developer Resources
- [AI Coding Assistants Setup](docs/ai-coding-assistants-setup.md) - VS Code, Cursor, Claude Code integration
- [API Reference](docs/registry_api.md) - Programmatic registry management
- [Dynamic Tool Discovery](docs/dynamic-tool-discovery.md) - Autonomous agent capabilities

### Operations
- [Production Deployment](docs/production-deployment.md) - High availability and scaling
- [Monitoring & Alerting](docs/monitoring.md) - Observability and health checks
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

---

## Community

### Get Involved

**Join the Discussion**
- [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions) - Feature requests and general discussion
- [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues) - Bug reports and feature requests

**Resources**
- [Demo Videos](https://github.com/agentic-community/mcp-gateway-registry#demo-videos) - See the platform in action
- [Blog Posts](docs/resources.md) - Technical deep-dives and use cases
- [Case Studies](docs/case-studies.md) - Real-world enterprise deployments

**Contributing**
- [Contributing Guide](CONTRIBUTING.md) - How to contribute code and documentation
- [Code of Conduct](CODE_OF_CONDUCT.md) - Community guidelines
- [Security Policy](SECURITY.md) - Responsible disclosure process

### Roadmap

**Upcoming Features**
- **Multi-Level Registry Support** - Federated registries with cross-IdP authentication
- **Usage Analytics Dashboard** - Comprehensive metrics and insights  
- **Tool Marketplace** - Community-driven MCP server discovery
- **KeyCloak Integration** - Additional enterprise IdP support

[📍 Full Roadmap](https://github.com/agentic-community/mcp-gateway-registry/milestones)

---

## License

This project is licensed under the Apache-2.0 License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**⭐ Star this repository if it helps your organization!**

[Get Started](docs/installation.md) | [Documentation](docs/) | [Contribute](CONTRIBUTING.md)

</div>
# Release v1.0.6 - A2A Protocol, AWS ECS Production Deployment & Federation

**November 2025**

---

## Major Features

### Agent-to-Agent (A2A) Protocol Support

Full implementation of the A2A protocol for agent registration, discovery, and communication:

- **Agent Registry API** - Complete REST API for agent lifecycle management (`/api/agents/*`)
- **Semantic Agent Discovery** - Find agents using natural language queries
- **Agent Health Checks** - Live `/ping` health monitoring for registered agents
- **Fine-Grained Access Control** - Three-tier permissions (UI-Scopes, Group Mappings, Agent Scopes)
- **Example Agents** - Travel Assistant and Flight Booking agents using Strands framework

[A2A Guide](docs/a2a.md) | [Agent Management](docs/a2a-agent-management.md)

### AWS ECS Production Deployment

Production-ready deployment on Amazon ECS Fargate:

- **Multi-AZ Architecture** - High availability across 2 availability zones
- **Auto-scaling** - Dynamic scaling based on CPU/memory utilization (2-4 tasks)
- **Aurora PostgreSQL Serverless v2** - Auto-scaling database with Multi-AZ replication
- **Application Load Balancers** - HTTPS/SSL termination with ACM certificates
- **CloudWatch Integration** - Comprehensive monitoring, logging, and alerting
- **EFS Shared Storage** - Persistent storage for models, logs, and configuration
- **Complete Terraform Configuration** - Infrastructure as Code for the entire stack

[ECS Deployment Guide](terraform/aws-ecs/README.md)

### Federated Registry (ASOR Integration)

Multi-registry federation support:

- **Workday ASOR Integration** - Import AI agents from Agent System of Record
- **Visual Identification** - Clear visual tags distinguish federation sources (ANTHROPIC, ASOR)
- **Automatic Sync** - Scheduled synchronization with external registries
- **Centralized Management** - Single control plane for all federated servers and agents

[Federation Guide](docs/federation.md)

### Microsoft Entra ID (Azure AD) Integration

Enterprise SSO with Microsoft identity platform:

- **Generic OIDC Support** - Flexible authentication provider configuration
- **Entra ID Provider** - Native Microsoft Entra ID integration
- **Group-Based Access Control** - Leverage existing Azure AD groups for permissions

[Entra ID Setup Guide](docs/entra-id-setup.md)

---

## What's New

### A2A Agent Features
- Agent registration, update, delete, and toggle operations
- Semantic search for agent discovery (`/api/agents/discover/semantic`)
- Skill-based agent discovery (`/api/agents/discover`)
- Live agent health checks with `/ping` endpoint validation
- Travel Assistant and Flight Booking example agents

### AWS ECS Deployment
- Production architecture with ECS Fargate
- Multi-account support for ALB security groups
- Scopes initialization container for Keycloak setup
- DockerHub publishing support for container images
- Architecture diagram for ECS deployment

### UI Improvements
- Dark mode as default theme
- Semantic search integration in Registry UI
- Agent toggle functionality (enable/disable agents)
- Agent cards with health status display
- Improved UX and removed redundant search button

### Developer Experience
- `DEV_INSTRUCTIONS.md` - Comprehensive developer onboarding guide
- `llms.txt` - LLM-friendly reference document for AI assistants
- API reference documentation with OpenAPI specs
- Agent management CLI (`cli/agent_mgmt.py`)
- Bootstrap script for user and M2M setup

### Infrastructure
- Keycloak realm-level SSL configuration
- Gateway host flexibility for multi-platform support
- Build configuration with `build-config.yaml` and enhanced Makefile

---

## Breaking Changes

None - this release is fully backward compatible with v1.0.5.

---

## Upgrade Instructions

### For Existing Installations

1. **Pull the latest changes:**
```bash
cd mcp-gateway-registry
git pull origin main
```

2. **Update environment configuration:**
Add new variables to your `.env` file if using federation or Entra ID:
```bash
# For ASOR federation
ASOR_ACCESS_TOKEN=your_token

# For Entra ID
ENTRA_CLIENT_ID=your_client_id
ENTRA_CLIENT_SECRET=your_client_secret
ENTRA_TENANT_ID=your_tenant_id
```

3. **Restart services:**
```bash
./build_and_run.sh
```

### For AWS ECS Deployment

See [ECS Deployment Guide](terraform/aws-ecs/README.md) for complete Terraform-based deployment instructions.

---

## Resources

- [A2A Protocol Guide](docs/a2a.md)
- [Agent Management Guide](docs/a2a-agent-management.md)
- [AWS ECS Deployment Guide](terraform/aws-ecs/README.md)
- [Federation Guide](docs/federation.md)
- [Entra ID Setup Guide](docs/entra-id-setup.md)
- [API Reference](docs/api-reference.md)
- [Developer Instructions](DEV_INSTRUCTIONS.md)

---

## Support

- [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)
- [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions)
- [Documentation](https://github.com/agentic-community/mcp-gateway-registry/tree/main/docs)

---

**Full Changelog:** [v1.0.5...v1.0.6](https://github.com/agentic-community/mcp-gateway-registry/compare/v1.0.5...v1.0.6)

# MCP Gateway Registry Helm Charts

This directory contains Helm charts for deploying the MCP Gateway Registry stack.

## Charts Overview

### Individual Charts

- **auth-server**: Authentication service for the MCP Gateway
- **registry**: MCP server registry service
- **keycloak-configure**: Job to configure Keycloak realms and clients

### Stack Chart

- **mcp-gateway-registry-stack**: Complete stack deployment including Keycloak, auth-server, registry, and configuration

## Improved Values Structure

The values files have been standardized with the following structure:

### Global Configuration

```yaml
global:
  image:
    repository: mcpgateway/service-name
    tag: v1.0.7
    pullPolicy: IfNotPresent
```

### Application Configuration

```yaml
app:
  name: service-name
  replicas: 1
  externalUrl: http://localhost:8080
  secretKey: your-secret-key
```

### Service Configuration

```yaml
service:
  type: ClusterIP
  port: 8080
  annotations: { }
```

### Resources

```yaml
resources:
  requests:
    cpu: 1
    memory: 1Gi
  limits:
    cpu: 2
    memory: 2Gi
```

### Ingress

```yaml
ingress:
  enabled: false
  className: alb
  hostname: ""
  annotations: { }
  tls: false
```

## Key Improvements

1. **Consistent Structure**: All charts now follow the same values organization
2. **Standardized Naming**: Unified naming conventions across all charts
3. **Reduced Duplication**: Eliminated redundant resource definitions
4. **Better Defaults**: Sensible default values for development and production
5. **Clean Templates**: Updated all templates to use the new values structure
6. **Clear Documentation**: Inline comments explaining configuration options

## Usage

### Deploy Individual Services

```bash
helm install auth-server ./charts/auth-server
helm install registry ./charts/registry
```

### Deploy Complete Stack

```bash
# Option 1: Update values.yaml file directly
# Edit charts/mcp-gateway-registry-stack/values.yaml and change global.domain

# Option 2: Override via command line
helm install mcp-stack ./charts/mcp-gateway-registry-stack \
  --set global.domain=yourdomain.com \
  --set global.secretKey=your-production-secret
```

## Configuration Notes

- **Domain**: The stack chart uses the domain from `global.domain` and applies it to all subcharts
- **Secret Keys**: Change default secret keys in production - they should match across all services
- **Resources**: Adjust CPU/memory based on your requirements
- **Ingress**: Configure ingress settings for your environment

### Domain Configuration

The stack chart uses `global.domain` to automatically configure all subdomains:

- `keycloak.{domain}` - Keycloak authentication server
- `auth-server.{domain}` - MCP Gateway auth server
- `mcpregistry.{domain}` - MCP server registry

**How it works:**

1. Set `global.domain` in the stack values file
2. All subchart templates reference `{{ .Values.global.domain }}` to build URLs and hostnames
3. Change the domain once and all services update automatically

**To change the domain:**

```bash
# Edit the values file
vim charts/mcp-gateway-registry-stack/values.yaml
# Change: global.domain: "your-new-domain.com"

# Or override via command line
helm upgrade mcp-stack ./charts/mcp-gateway-registry-stack \
  --set global.domain=your-new-domain.com
```

Make sure your DNS is configured to point these subdomains to your Kubernetes ingress.
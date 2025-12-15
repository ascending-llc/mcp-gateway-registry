# MCP Gateway Registry Stack Charts

This collection of charts deploys everything needed to install the MCP Gateway Registry using Helm or ArgoCD.

## Prerequisites

### Amazon EKS Cluster

For production deployments, we recommend using the [AWS AI/ML on Amazon EKS](https://github.com/awslabs/ai-on-eks) blueprints to provision a production-ready EKS cluster:

```bash
# Clone AI on EKS repository
git clone https://github.com/awslabs/ai-on-eks.git
cd ai-on-eks

# Until https://github.com/awslabs/ai-on-eks/pull/232 is merged, the custom stack can be used

cd infra/custom
./install.sh
```

The ai-on-eks blueprints provide:
- GPU support for AI/ML workloads
- Karpenter for efficient auto-scaling
- EKS-optimized configurations
- Security best practices
- Observability with Prometheus/Grafana
- Proven, battle-tested infrastructure

### Additional Requirements

- `helm` CLI installed (v3.0+)
- `kubectl` configured to access your EKS cluster
- AWS Load Balancer Controller for EKS
- ExternalDNS (optional, for automatic DNS management)
- Domain name with DNS access
- TLS certificates (AWS Certificate Manager or Let's Encrypt)

## Setup

```
git clone https://github.com/agentic-community/mcp-gateway-registry
cd mcp-gateway-registry/charts/mcp-gateway-registry-stack
```

## Values file

The `values.yaml` file needs to be updated for your setup, specifically:

- `DOMAIN`: there are placeholders for `DOMAIN` that should be updated with your full domain. For example, if you intend
  to use `example.com`, replace `DOMAIN` with `example.com`. If you intend to use a subdomain like
  `subdomain.example.com`, `DOMAIN` should be replaced with `subdomain.example.com`
- `secretKey`: the registry and auth-server both have a placeholder for `secretKey`, this should be updated to the same
  random, secure key that is used in both locations

## Install

Once the `values.yaml` file is updated and saved, run (substitute MYNAMESPACE for the namespace in which this should be
installed):

```bash
helm dependency build && helm dependency update
helm install mcp-gateway-registry -n MYNAMESPACE --create-namespace . 
```

This will deploy the necessary resources for a Kubernetes deployment of the MCP Gateway Registry

## Deploy Process

- postgres, keycloak, registry, and auth-server will be deployed as the core components
- A `keycloak-configure` job will also be created
- Postgres will need to be running first before Keycloak will run
- Keycloak needs to be available before the `keycloak-configure` job will run
- auth-server will not start until the `keycloak-configure` job has succeeded and generated a secret that is needed for
  the auth-server.
- The registry will start as soon as the image is pulled

## Use

Navigate to https://mcpregistry.DOMAIN to log in. The username/password are displayed in the output of the
`keycloak-configure job`

```bash
kubectl get pods -l job-name=setup-keycloak -n MYNAMESPACE     
```

The output will look similar to:

```
NAME                   READY   STATUS      RESTARTS   AGE
setup-keycloak-d6g2r   0/1     Completed   0          29m
setup-keycloak-nnqgj   0/1     Error       0          31m
```

Use the pod name that completed successfully:

```
kubectl logs -n MYNAMESPACE setup-keycloak-d6g2r --tail 20
```

You will see the credentials in the output

# MCP Security Scanner - Supply Chain Security for MCP Servers and A2A Agents

## Introduction

As organizations integrate Model Context Protocol (MCP) servers and Agent-to-Agent (A2A) agents into their AI workflows, supply chain security becomes critical. These third-party components provide tools and capabilities to AI systems, making them potential vectors for security vulnerabilities, malicious code injection, and data exfiltration.

The MCP Gateway Registry addresses this challenge by integrating automated security scanning powered by two specialized tools:

- **[Cisco AI Defence MCP Scanner](https://github.com/cisco-ai-defense/mcp-scanner)** - For MCP server security analysis
- **[Cisco AI Defence A2A Scanner](https://github.com/cisco-ai-defense/a2a-scanner)** - For Agent-to-Agent protocol security analysis

These open-source security tools perform deep analysis of MCP servers and A2A agents to identify vulnerabilities before they can be exploited in production environments.

**GitHub Repositories:**
- MCP Scanner: https://github.com/cisco-ai-defense/mcp-scanner
- A2A Scanner: https://github.com/cisco-ai-defense/a2a-scanner

### Security Scanning Workflows

The registry implements multiple complementary security scanning workflows for both MCP servers and A2A agents:

#### MCP Server Scanning
1. **Automated Scanning During Server Registration** - Every new server is scanned before being made available to AI agents
2. **Manual On-Demand Scans via API** - Administrators can trigger security scans for specific servers
3. **Query Scan Results via API** - View detailed security scan results for any registered server
4. **Periodic Registry Scans** - Comprehensive security audits across all enabled servers in the registry

#### A2A Agent Scanning
1. **Automated Scanning During Agent Registration** - Every new agent is scanned before being enabled in the registry
2. **Manual On-Demand Agent Scans via API** - Administrators can trigger security scans for specific agents
3. **Query Agent Scan Results** - View detailed security scan results for any registered agent

These workflows ensure continuous security monitoring throughout the MCP server and A2A agent lifecycle, from initial registration through ongoing operations.

## Security Scanning During Server Registration

When adding a new MCP server to the registry, a security scan is automatically performed as part of the registration workflow. This pre-deployment scanning prevents vulnerable or malicious servers from being exposed to AI agents.

### Command Format

```bash
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost register --config <config-file>
```

**Parameters:**
- `<config-file>`: JSON configuration file containing server details
- Security scanning is automatically enabled by default (configured via environment variables)

**Environment Variables for Security Scanning:**
- `SECURITY_SCAN_ENABLED=true` - Enable/disable security scanning (default: true)
- `SECURITY_SCAN_ON_REGISTRATION=true` - Scan during registration (default: true)
- `SECURITY_SCAN_BLOCK_UNSAFE_SERVERS=true` - Auto-disable unsafe servers (default: true)
- `SECURITY_ANALYZERS=yara` - Comma-separated list of analyzers (default: yara)
- `SECURITY_SCAN_TIMEOUT=60` - Scan timeout in seconds (default: 60)
- `MCP_SCANNER_LLM_API_KEY=<key>` - API key for LLM analyzer (optional)

### Example: Registering Cloudflare Documentation Server

**Configuration File** (`cli/examples/cloudflare-docs-server-config.json`):

```json
{
  "server_name": "Cloudflare Documentation MCP Server",
  "description": "Search Cloudflare documentation and get migration guides",
  "path": "/cloudflare-docs",
  "proxy_pass_url": "https://docs.mcp.cloudflare.com/mcp",
  "supported_transports": ["streamable-http"]
}
```

**Registering the Server (Security Scan Automatic):**

```bash
# Register with automatic security scan (default YARA analyzer)
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost register --config cli/examples/cloudflare-docs-server-config.json

# To use LLM analyzer, set environment variable first
export MCP_SCANNER_LLM_API_KEY=sk-your-api-key
export SECURITY_ANALYZERS=yara,llm
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost register --config cli/examples/cloudflare-docs-server-config.json
```

### Security Scan Results

The scanner analyzes each tool provided by the MCP server and generates a detailed security report. Here's an example of scan results for the Cloudflare Documentation server:

**Scan Output** (`security_scans/docs.mcp.cloudflare.com_mcp.json`):

```json
{
  "analysis_results": {
    "yara_analyzer": {
      "findings": [
        {
          "tool_name": "search_cloudflare_documentation",
          "severity": "SAFE",
          "threat_names": [],
          "threat_summary": "No threats detected",
          "is_safe": true
        },
        {
          "tool_name": "migrate_pages_to_workers_guide",
          "severity": "SAFE",
          "threat_names": [],
          "threat_summary": "No threats detected",
          "is_safe": true
        }
      ]
    }
  },
  "tool_results": [
    {
      "tool_name": "search_cloudflare_documentation",
      "tool_description": "Search the Cloudflare documentation...",
      "status": "completed",
      "is_safe": true,
      "findings": {
        "yara_analyzer": {
          "severity": "SAFE",
          "threat_names": [],
          "threat_summary": "No threats detected",
          "total_findings": 0
        }
      }
    },
    {
      "tool_name": "migrate_pages_to_workers_guide",
      "tool_description": "ALWAYS read this guide before migrating Pages projects to Workers.",
      "status": "completed",
      "is_safe": true,
      "findings": {
        "yara_analyzer": {
          "severity": "SAFE",
          "threat_names": [],
          "threat_summary": "No threats detected",
          "total_findings": 0
        }
      }
    }
  ]
}
```

### What Happens When a Scan Fails

If the security scan detects critical or high severity vulnerabilities:

1. **Server is Added but Disabled** - The server is registered in the database but marked as `disabled`
2. **Security-Pending Tag** - The server receives a `security-pending` tag to flag it for review
3. **AI Agents Cannot Access** - Disabled servers are excluded from agent discovery and tool routing
4. **Visible in UI** - The server appears in the registry UI with clear indicators of its security status
5. **Detailed Report Generated** - A comprehensive JSON report is saved to `security_scans/` directory

**Console Output for Failed Scan:**

```
=== Security Scan ===
Scanning server for security vulnerabilities...
Security scan failed - Server has critical or high severity issues
Server will be registered but marked as UNHEALTHY with security-pending status

Security Issues Found:
  Critical: 2
  High: 3
  Medium: 1
  Low: 0

Detailed report: security_scans/scan_example.com_mcp_20251022_103045.json

=== Security Status Update ===
Marking server as UNHEALTHY due to failed security scan...
Server registered but flagged as security-pending
Review the security scan report before enabling this server

Service example-server successfully added and verified
WARNING: Server failed security scan - Review required before use
```

**Screenshot:**

![Failed Security Scan - Server in Disabled State with Security-Pending Tag](img/failed_scan.png)

*Servers that fail security scans are automatically added in disabled state with a `security-pending` tag, requiring administrator review before being enabled.*

This workflow ensures that vulnerable servers never become accessible to AI agents without explicit administrator review and remediation.

## Manual On-Demand Security Scans (API)

Administrators can trigger manual security scans for specific servers using the REST API or CLI commands. This is useful for:
- Re-scanning servers after updates or patches
- On-demand security assessments
- Validating security fixes
- Regular compliance checks

### API Endpoints

#### Trigger Security Scan (Admin Only)

**Endpoint:** `POST /api/servers/{path}/rescan`

**Description:** Initiates a new security scan for the specified server and returns the results.

**Authentication:** JWT Bearer token or session cookie

**Authorization:** Requires admin privileges

**Example using CLI:**

```bash
# Trigger security scan for a specific server
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost rescan --path /cloudflare-docs
```

**Example Output:**

```
Security scan completed for server '/cloudflare-docs':
  Status: SAFE
  Scan timestamp: 2025-12-15T15:24:46.956393Z
  Analyzers used: yara

  Severity counts:
    Critical: 0
    High: 0
    Medium: 0
    Low: 0
```

**Example using curl:**

```bash
curl -X POST http://localhost/api/servers/cloudflare-docs/rescan \
  -H "Authorization: Bearer $JWT_TOKEN"
```

#### Query Scan Results

**Endpoint:** `GET /api/servers/{path}/security-scan`

**Description:** Retrieves the latest security scan results for a server, including detailed threat analysis and tool-level findings.

**Authentication:** JWT Bearer token or session cookie

**Authorization:** Requires admin privileges or access to the server

**Example using CLI:**

```bash
# Get security scan results
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost security-scan --path /cloudflare-docs

# Get results in JSON format
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost security-scan --path /cloudflare-docs --json
```

**Example Output:**

```
Security scan results for server '/cloudflare-docs':

  Analyzer: yara_analyzer
    Findings: 2
      - search_cloudflare_documentation: SAFE
      - migrate_pages_to_workers_guide: SAFE

  Total tools scanned: 2
  Safe tools: 2
```

**Example using curl:**

```bash
curl -X GET http://localhost/api/servers/cloudflare-docs/security-scan \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Python Client Library

The registry includes a Python client library with built-in security scan support:

```python
from api.registry_client import RegistryClient

# Initialize client
client = RegistryClient(
    registry_url="http://localhost",
    token_file=".oauth-tokens/ingress.json"
)

# Trigger security scan
scan_result = client.rescan_server(path="/cloudflare-docs")
print(f"Scan Status: {'SAFE' if scan_result.is_safe else 'UNSAFE'}")
print(f"Critical Issues: {scan_result.critical_issues}")

# Get scan results
results = client.get_security_scan(path="/cloudflare-docs")
for analyzer_name, analyzer_data in results.analysis_results.items():
    print(f"Analyzer: {analyzer_name}")
    print(f"  Findings: {len(analyzer_data.get('findings', []))}")
```

### Scan Results Storage

All security scan results are automatically saved to the `security_scans/` directory:

- **Latest Scans:** `security_scans/<server-url>.json`
- **Archived Scans:** `security_scans/YYYY-MM-DD/scan_<server-url>_YYYYMMDD_HHMMSS.json`

The results can be queried via the API or accessed directly from the filesystem.

## A2A Agent Security Scanning

The registry provides comprehensive security scanning for Agent-to-Agent (A2A) protocol agents using the [Cisco AI Defence A2A Scanner](https://github.com/cisco-ai-defense/a2a-scanner). This ensures that agents registered in the system are safe and compliant with security standards before being made available.

### Automated Scanning During Agent Registration

When registering a new A2A agent, security scanning is automatically performed as part of the registration workflow.

**Command Format:**

```bash
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-register --config <agent-card-file>
```

**Environment Variables for Agent Security Scanning:**
- `AGENT_SECURITY_SCAN_ENABLED=true` - Enable/disable agent security scanning (default: true)
- `AGENT_SECURITY_SCAN_ON_REGISTRATION=true` - Scan during registration (default: true)
- `AGENT_SECURITY_BLOCK_UNSAFE_AGENTS=true` - Auto-disable unsafe agents (default: true)
- `AGENT_SECURITY_ANALYZERS=yara,spec` - Comma-separated list of analyzers (default: yara,spec)
- `AGENT_SECURITY_SCAN_TIMEOUT=60` - Scan timeout in seconds (default: 60)
- `AGENT_SECURITY_ADD_PENDING_TAG=true` - Add security-pending tag to unsafe agents (default: true)

**Example: Registering Flight Booking Agent**

```bash
# Register agent with automatic security scan
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-register \
  --config cli/examples/flight_booking_agent_card.json
```

**Example Output:**

```json
{
  "message": "Agent registered successfully",
  "agent": {
    "name": "Flight Booking Agent",
    "path": "/flight-booking",
    "url": "http://flight-booking-agent:9000/",
    "num_skills": 5,
    "is_enabled": true
  }
}
```

The agent is automatically enabled if it passes the security scan. If vulnerabilities are detected, the agent is registered but disabled with a `security-pending` tag.

### Manual On-Demand Agent Scans (API)

Administrators can trigger manual security scans for specific agents using CLI commands or the REST API.

#### Trigger Agent Security Scan (Admin Only)

**Endpoint:** `POST /api/agents/{path}/rescan`

**Description:** Initiates a new security scan for the specified agent and returns the results.

**Authentication:** JWT Bearer token or session cookie

**Authorization:** Requires admin privileges

**Example using CLI:**

```bash
# Trigger security scan for a specific agent
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-rescan --path /flight-booking
```

**Example Output:**

```
Security scan completed for agent '/flight-booking':
  Status: SAFE
  Scan timestamp: 2025-12-17T19:05:37.499170Z
  Analyzers used: yara, spec

  Severity counts:
    Critical: 0
    High: 0
    Medium: 0
    Low: 0

  Output file: /app/agent_security_scans/flight-booking.json
```

**Example with JSON output:**

```bash
# Get JSON format output
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-rescan --path /flight-booking --json
```

### Query Agent Scan Results

Agent security scan results are stored in the `agent_security_scans/` directory and can be accessed directly:

**Storage Locations:**
- **Latest Scans:** `agent_security_scans/<agent-path>.json`
- **Archived Scans:** `agent_security_scans/YYYY-MM-DD/scan_<agent-path>_YYYYMMDD_HHMMSS.json`

**Viewing scan results:**

```bash
# Set registry container variable
export REGISTRY_CONTAINER=$(docker ps --filter "name=registry" --format "{{.Names}}" | grep "registry-1")

# View scan results inside container
docker exec $REGISTRY_CONTAINER cat /app/agent_security_scans/flight-booking.json | jq '.'

# Copy scan results to local machine
docker cp $REGISTRY_CONTAINER:/app/agent_security_scans/flight-booking.json ./flight_booking_scan.json
```

**Example Scan Result:**

```json
{
  "analysis_results": {},
  "scan_results": {
    "target_name": "Flight Booking Agent",
    "target_type": "agent_card",
    "status": "completed",
    "analyzers": ["yara", "heuristic", "spec", "endpoint"],
    "findings": [],
    "metadata": {
      "agent_id": null,
      "url": "http://flight-booking-agent:9000/"
    },
    "total_findings": 0,
    "high_severity_count": 0
  }
}
```

### Python Client Library for Agent Scanning

```python
from api.registry_client import RegistryClient

# Initialize client
client = RegistryClient(
    registry_url="http://localhost",
    token_file=".oauth-tokens/ingress.json"
)

# Trigger agent security scan
scan_result = client.rescan_agent(path="/flight-booking")
print(f"Scan Status: {'SAFE' if scan_result.is_safe else 'UNSAFE'}")
print(f"Critical Issues: {scan_result.critical_issues}")
print(f"Analyzers Used: {', '.join(scan_result.analyzers_used)}")
```

### What Happens When an Agent Scan Fails

If the security scan detects critical or high severity vulnerabilities:

1. **Agent is Registered but Disabled** - The agent is added to the database but marked as `is_enabled=false`
2. **Security-Pending Tag** - The agent receives a `security-pending` tag to flag it for review
3. **Excluded from Discovery** - Disabled agents are not returned in agent discovery queries
4. **Detailed Report Generated** - A comprehensive JSON report is saved to `agent_security_scans/` directory

Administrators must review the security scan results and remediate any issues before manually enabling the agent.

## Periodic Registry Scans

Beyond initial registration security checks, the registry supports comprehensive periodic scans of all enabled servers. This ongoing monitoring detects newly discovered vulnerabilities and ensures continued security compliance.

### Command to Run Periodic Scans

```bash
cd /home/ubuntu/repos/mcp-gateway-registry
uv run cli/scan_all_servers.py --base-url https://mcpgateway.example.com
```

**Command Options:**

```bash
# Scan with default YARA analyzer
uv run cli/scan_all_servers.py --base-url https://mcpgateway.example.com

# Scan with both YARA and LLM analyzers (requires API key in .env)
uv run cli/scan_all_servers.py --base-url https://mcpgateway.example.com --analyzers yara,llm

# Specify custom output directory
uv run cli/scan_all_servers.py --base-url https://mcpgateway.example.com --output-dir custom_scans
```

### Generated Report

The periodic scan generates a comprehensive markdown report that provides an executive summary and detailed vulnerability breakdown for each server in the registry.

**Report Locations:**
- **Latest Report:** `security_scans/scan_report.md` (always current)
- **Archived Reports:** `security_scans/reports/scan_report_YYYYMMDD_HHMMSS.md` (timestamped history)

For a complete example of the report format and structure, see [scan_report_example.md](scan_report_example.md).

### Report Contents

The generated security report includes:

1. **Executive Summary**
   - Total servers scanned
   - Pass/fail statistics
   - Overall security posture metrics

2. **Aggregate Vulnerability Statistics**
   - Total count by severity level (Critical, High, Medium, Low)
   - Trend analysis across multiple scans

3. **Per-Server Vulnerability Breakdown**
   - Individual server security status
   - Severity distribution per server
   - Scan timestamp and analyzer information

4. **Detailed Findings for Vulnerable Tools**
   - Specific tool names and descriptions
   - Threat categories and taxonomy
   - AI Security Framework (AITech) classification
   - Remediation guidance

**Example Report Summary:**

---

# MCP Server Security Scan Report

**Scan Date:** 2025-10-21 23:50:03 UTC
**Analyzers Used:** yara

## Executive Summary

- **Total Servers Scanned:** 6
- **Passed:** 2 (33.3%)
- **Failed:** 4 (66.7%)

### Aggregate Vulnerability Statistics

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 3 |
| Medium | 0 |
| Low | 0 |

---

These reports enable security teams to track vulnerability trends, prioritize remediation efforts, and maintain compliance with organizational security policies.

## Analyzers

The MCP Scanner supports two analyzer types, each with distinct capabilities and use cases:

### YARA Analyzer

**Type:** Pattern-based detection
**Speed:** Fast (seconds per server)
**API Key Required:** No
**Best For:** Known threat patterns, common vulnerabilities

The YARA analyzer uses signature-based detection rules to identify known security threats including:
- SQL injection patterns
- Command injection vulnerabilities
- Cross-site scripting (XSS) vectors
- Path traversal attempts
- Hardcoded credentials
- Malicious code patterns

YARA scanning is ideal for automated workflows and continuous integration pipelines due to its speed and zero-configuration requirements.

### LLM Analyzer

**Type:** AI-powered semantic analysis
**Speed:** Slower (requires API calls)
**API Key Required:** Yes (OpenAI-compatible API)
**Best For:** Sophisticated threats, zero-day vulnerabilities, context-aware analysis

The LLM analyzer uses large language models to perform deep semantic analysis of tool code and descriptions. It can detect:
- Subtle logic vulnerabilities
- Context-dependent security issues
- Novel attack patterns
- Business logic flaws
- Privacy concerns in data handling

LLM scanning is recommended for high-value or high-risk MCP servers where comprehensive security analysis justifies the additional time and API costs.

### Analyzer Comparison

| Feature | YARA | LLM | Both |
|---------|------|-----|------|
| **Speed** | Fast (seconds) | Slower (minutes) | Slower |
| **API Key** | Not required | Required | Required |
| **Detection Type** | Pattern-based | Semantic analysis | Comprehensive |
| **False Positives** | Low | Medium | Low |
| **Coverage** | Known threats | Known + novel threats | Maximum |
| **Use Case** | Automated scans, CI/CD | Critical servers, deep analysis | High-security environments |

### Configuring LLM Analyzer

To use the LLM analyzer, set the API key in your `.env` file:

```bash
# Add to .env file
MCP_SCANNER_LLM_API_KEY=sk-your-openai-api-key
```

**Using Both Analyzers:**

```bash
# During server addition
./cli/service_mgmt.sh add config.json yara,llm

# During periodic scans
uv run cli/scan_all_servers.py --base-url https://mcpgateway.example.com --analyzers yara,llm
```

### Recommendation

- **Default (YARA only):** Suitable for most use cases, provides fast scanning with no API costs
- **Add LLM:** For critical production servers, sensitive data environments, or when unknown threats are a concern
- **Both analyzers:** Recommended for maximum security coverage in high-stakes deployments

The combination of both analyzers provides defense-in-depth, with YARA catching known threats quickly and LLM performing deeper analysis for sophisticated attacks.

## Prerequisites

### Set LLM API Key (Optional)

Only required if using the LLM analyzer:

```bash
# Add to .env file (recommended)
echo "MCP_SCANNER_LLM_API_KEY=sk-your-api-key" >> .env
```

## Troubleshooting

### API Key Issues

If you see errors about missing API keys when using the LLM analyzer:

```bash
# Verify the key is set
echo $MCP_SCANNER_LLM_API_KEY

# Add to .env file
echo "MCP_SCANNER_LLM_API_KEY=sk-your-key" >> .env
```

Note: The scanner uses `MCP_SCANNER_LLM_API_KEY`, not `OPENAI_API_KEY`.

### Permission Issues

Ensure the `security_scans/` directory is writable:

```bash
mkdir -p security_scans
chmod 755 security_scans
```

## Additional Resources

### Documentation
- **Cisco AI Defence MCP Scanner:** https://github.com/cisco-ai-defense/mcp-scanner
- **Cisco AI Defence A2A Scanner:** https://github.com/cisco-ai-defense/a2a-scanner
- **Example Report:** [scan_report_example.md](scan_report_example.md)

### CLI Tools
- **Registry Management CLI:** `api/registry_management.py` - Main CLI for server and agent registration with security scanning
- **Periodic Scan Script:** `cli/scan_all_servers.py` - Comprehensive registry-wide security audits for MCP servers

### MCP Server API Endpoints
- **Trigger Server Scan:** `POST /api/servers/{path}/rescan` - Admin-only manual security scan for MCP servers
- **Query Server Results:** `GET /api/servers/{path}/security-scan` - Retrieve MCP server scan results

### A2A Agent API Endpoints
- **Trigger Agent Scan:** `POST /api/agents/{path}/rescan` - Admin-only manual security scan for A2A agents
- **Query Agent Results:** `GET /api/agents/{path}/security-scan` - Retrieve A2A agent scan results (file system access recommended)

### Registry Management CLI Commands

#### MCP Server Security Commands
```bash
# Trigger server security scan
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost rescan --path /server-path

# Get server scan results
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost security-scan --path /server-path
```

#### A2A Agent Security Commands
```bash
# Trigger agent security scan
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-rescan --path /agent-path

# Get agent scan results (with JSON output)
uv run python api/registry_management.py --token-file .oauth-tokens/ingress.json \
  --registry-url http://localhost agent-rescan --path /agent-path --json
```

### Python Client
- **Registry Client:** `api/registry_client.py` - Python library with security scanning methods:
  - `rescan_server(path)` - Trigger MCP server security scan
  - `get_security_scan(path)` - Get MCP server scan results
  - `rescan_agent(path)` - Trigger A2A agent security scan
  - `get_agent_security_scan(path)` - Get A2A agent scan results

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

## Per-Server Scan Results

### io.mcpgateway/atlassian

- **URL:** `https://mcpgateway.ddns.net/atlassian/mcp`
- **Status:** ❌ UNSAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 2 |
| Medium | 0 |
| Low | 0 |

#### Detailed Findings

**Tool: `jira_get_user_profile`**

- **Analyzer:** yara_analyzer
- **Severity:** HIGH
- **Threats:** INJECTION ATTACK
- **Summary:** Detected 1 threat: sql injection

**Taxonomy:**
```json
{
  "scanner_category": "INJECTION ATTACK",
  "aitech": "AITech-9.1",
  "aitech_name": "Model or Agentic System Manipulation",
  "aisubtech": "AISubtech-9.1.4",
  "aisubtech_name": "Injection Attacks (SQL, Command Execution, XSS)",
  "description": "Injecting malicious payloads such as SQL queries, command sequences, or scripts into MCP servers or tools that process model or user input, leading to data exposure, remote code execution, or compromise of the underlying system environment."
}
```

<details>
<summary>Tool Description</summary>

```

    Retrieve profile information for a specific Jira user.

    Args:
        ctx: The FastMCP context.
        user_identifier: User identifier (email, username, key, or account ID).

    Returns:
        JSON string representing the Jira user profile object, or an error object if not found.

    Raises:
        ValueError: If the Jira client is not configured or available.
    
```
</details>

**Tool: `jira_get_agile_boards`**

- **Analyzer:** yara_analyzer
- **Severity:** HIGH
- **Threats:** INJECTION ATTACK
- **Summary:** Detected 1 threat: sql injection

**Taxonomy:**
```json
{
  "scanner_category": "INJECTION ATTACK",
  "aitech": "AITech-9.1",
  "aitech_name": "Model or Agentic System Manipulation",
  "aisubtech": "AISubtech-9.1.4",
  "aisubtech_name": "Injection Attacks (SQL, Command Execution, XSS)",
  "description": "Injecting malicious payloads such as SQL queries, command sequences, or scripts into MCP servers or tools that process model or user input, leading to data exposure, remote code execution, or compromise of the underlying system environment."
}
```

<details>
<summary>Tool Description</summary>

```
Get jira agile boards by name, project key, or type.

    Args:
        ctx: The FastMCP context.
        board_name: Name of the board (fuzzy search).
        project_key: Project key.
        board_type: Board type ('scrum' or 'kanban').
        start_at: Starting index.
        limit: Maximum results.

    Returns:
        JSON string representing a list of board objects.
    
```
</details>

**Error:** Scanner exit code: 1

### io.mcpgateway/currenttime

- **URL:** `https://mcpgateway.ddns.net/currenttime/mcp`
- **Status:** ✅ SAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

### io.mcpgateway/fininfo

- **URL:** `https://mcpgateway.ddns.net/fininfo/mcp`
- **Status:** ✅ SAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

**Error:** Scanner exit code: 1

### io.mcpgateway/mcpgw

- **URL:** `https://mcpgateway.ddns.net/mcpgw/mcp`
- **Status:** ❌ UNSAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 1 |
| Medium | 0 |
| Low | 0 |

#### Detailed Findings

**Tool: `healthcheck`**

- **Analyzer:** yara_analyzer
- **Severity:** HIGH
- **Threats:** INJECTION ATTACK
- **Summary:** Detected 1 threat: sql injection

**Taxonomy:**
```json
{
  "scanner_category": "INJECTION ATTACK",
  "aitech": "AITech-9.1",
  "aitech_name": "Model or Agentic System Manipulation",
  "aisubtech": "AISubtech-9.1.4",
  "aisubtech_name": "Injection Attacks (SQL, Command Execution, XSS)",
  "description": "Injecting malicious payloads such as SQL queries, command sequences, or scripts into MCP servers or tools that process model or user input, leading to data exposure, remote code execution, or compromise of the underlying system environment."
}
```

<details>
<summary>Tool Description</summary>

```
Retrieves health status information from all registered MCP servers via the registry's internal API.

Returns:
    Dict[str, Any]: Health status information for all registered servers, including:
        - status: 'healthy' or 'disabled'
        - last_checked_iso: ISO timestamp of when the server was last checked
        - num_tools: Number of tools provided by the server

Raises:
    Exception: If the API call fails or data cannot be retrieved
```
</details>

**Error:** Scanner exit code: 1

### io.mcpgateway/realserverfaketools

- **URL:** `https://mcpgateway.ddns.net/realserverfaketools/mcp`
- **Status:** ✅ SAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

### io.mcpgateway/sre-gateway

- **URL:** `https://mcpgateway.ddns.net/sre-gateway/mcp`
- **Status:** ✅ SAFE

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

**Error:** Scanner exit code: 1

---

*Report generated on 2025-10-21 23:50:03 UTC*

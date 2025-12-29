#!/usr/bin/env python3
"""
Scan all enabled MCP servers for security vulnerabilities.

This script:
1. Uses the Registry Management API client to get a list of all servers
2. Filters for enabled servers
3. Runs security scans on each enabled server using mcp_security_scanner.py

Usage:
    uv run python cli/scan_all_servers.py
    uv run python cli/scan_all_servers.py --base-url http://localhost
    uv run python cli/scan_all_servers.py --analyzers yara,llm
    uv run python cli/scan_all_servers.py --token-file .oauth-tokens/ingress.json
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path to import registry client
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "api"))

from registry_client import RegistryClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Constants
DEFAULT_TOKEN_FILE = PROJECT_ROOT / ".oauth-tokens" / "ingress.json"
DEFAULT_BASE_URL = "http://localhost"
DEFAULT_ANALYZERS = "yara"


def _run_security_scan(
    server_url: str,
    analyzers: str,
    api_key: Optional[str] = None,
    access_token: Optional[str] = None
) -> Dict[str, Any]:
    """Run security scan on a server using mcp_security_scanner.py directly.

    Args:
        server_url: URL of the MCP server to scan
        analyzers: Comma-separated list of analyzers (e.g., 'yara', 'yara,llm')
        api_key: Optional API key for LLM analyzer
        access_token: Optional access token for authenticated MCP servers

    Returns:
        Dictionary with scan results including:
        - success: bool
        - scan_output_file: Path to scan results JSON file
        - critical_issues: int
        - high_severity: int
        - medium_severity: int
        - low_severity: int
        - is_safe: bool
    """
    scanner_script = SCRIPT_DIR / "mcp_security_scanner.py"

    if not scanner_script.exists():
        logger.error(f"mcp_security_scanner.py not found at: {scanner_script}")
        return {
            "success": False,
            "scan_output_file": None,
            "critical_issues": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "is_safe": False,
            "error_message": "Scanner script not found"
        }

    cmd = [
        "uv", "run", "python",
        str(scanner_script),
        "--server-url", server_url,
        "--analyzers", analyzers
    ]

    if api_key:
        cmd.extend(["--api-key", api_key])

    # Add headers with authorization token if provided
    if access_token:
        headers_json = json.dumps({"X-Authorization": f"Bearer {access_token}"})
        cmd.extend(["--headers", headers_json])

    # Log command with masked token for security
    cmd_for_log = cmd.copy()
    if access_token and "--headers" in cmd_for_log:
        header_idx = cmd_for_log.index("--headers") + 1
        headers_masked = json.dumps({"X-Authorization": f"Bearer {access_token[:20]}...{access_token[-10:]}"})
        cmd_for_log[header_idx] = headers_masked
    logger.info(f"Running: {' '.join(cmd_for_log)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(PROJECT_ROOT)
        )

        # Log output
        if result.stdout:
            logger.info(f"Scan output:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"Scan stderr:\n{result.stderr}")

        # Parse scan results from security_scans directory
        scan_result = {
            "success": result.returncode == 0,
            "scan_output_file": None,
            "critical_issues": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "is_safe": result.returncode == 0,
            "error_message": None
        }

        # Try to find and parse the scan output file
        try:
            # Extract server name from URL for finding scan file
            from urllib.parse import urlparse
            parsed = urlparse(server_url)
            path_parts = [p for p in parsed.path.split('/') if p and p != 'mcp']
            if path_parts:
                server_name = path_parts[0]
                scan_file = PROJECT_ROOT / "security_scans" / f"{server_name}_mcp.json"

                if scan_file.exists():
                    scan_result["scan_output_file"] = str(scan_file)
                    with open(scan_file, 'r') as f:
                        scan_data = json.load(f)

                    # Extract severity counts from analysis_results
                    analysis_results = scan_data.get("analysis_results", {})
                    for analyzer_name, analyzer_data in analysis_results.items():
                        if isinstance(analyzer_data, dict):
                            findings = analyzer_data.get("findings", [])
                            for finding in findings:
                                severity = finding.get("severity", "").lower()
                                if severity == "critical":
                                    scan_result["critical_issues"] += 1
                                elif severity == "high":
                                    scan_result["high_severity"] += 1
                                elif severity == "medium":
                                    scan_result["medium_severity"] += 1
                                elif severity == "low":
                                    scan_result["low_severity"] += 1

                    # Determine if safe based on scan data
                    scan_result["is_safe"] = (scan_result["critical_issues"] == 0 and
                                             scan_result["high_severity"] == 0)
        except Exception as e:
            logger.warning(f"Could not parse scan results: {e}")

        # Check exit code
        if result.returncode == 0:
            logger.info("✓ Scan completed successfully")
        else:
            logger.error(f"✗ Scan failed with exit code: {result.returncode}")
            scan_result["error_message"] = f"Scanner exit code: {result.returncode}"

        return scan_result

    except Exception as e:
        logger.error(f"Failed to run scan: {e}")
        return {
            "success": False,
            "scan_output_file": None,
            "critical_issues": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "is_safe": False,
            "error_message": str(e)
        }


def _generate_markdown_report(
    scan_results: List[Dict[str, Any]],
    stats: Dict[str, int],
    analyzers: str,
    scan_timestamp: str
) -> str:
    """Generate markdown report from scan results.

    Args:
        scan_results: List of scan result dictionaries
        stats: Dictionary with summary statistics
        analyzers: Analyzers used for scanning
        scan_timestamp: ISO timestamp of scan

    Returns:
        Markdown formatted report as string
    """
    lines = []

    # Header
    lines.append("# MCP Server Security Scan Report")
    lines.append("")
    lines.append(f"**Scan Date:** {scan_timestamp}")
    lines.append(f"**Analyzers Used:** {analyzers}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    total = stats['total']
    passed = stats['passed']
    failed = stats['failed']
    pass_rate = (passed / total * 100) if total > 0 else 0

    lines.append(f"- **Total Servers Scanned:** {total}")
    lines.append(f"- **Passed:** {passed} ({pass_rate:.1f}%)")
    lines.append(f"- **Failed:** {failed} ({100 - pass_rate:.1f}%)")
    lines.append("")

    # Aggregate Vulnerability Statistics
    total_critical = sum(r.get('critical_issues', 0) for r in scan_results)
    total_high = sum(r.get('high_severity', 0) for r in scan_results)
    total_medium = sum(r.get('medium_severity', 0) for r in scan_results)
    total_low = sum(r.get('low_severity', 0) for r in scan_results)

    lines.append("### Aggregate Vulnerability Statistics")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Critical | {total_critical} |")
    lines.append(f"| High | {total_high} |")
    lines.append(f"| Medium | {total_medium} |")
    lines.append(f"| Low | {total_low} |")
    lines.append("")

    # Per-Server Results
    lines.append("## Per-Server Scan Results")
    lines.append("")

    for result in scan_results:
        server_name = result.get('server_name', 'Unknown')
        server_url = result.get('server_url', 'Unknown')
        is_safe = result.get('is_safe', False)
        status = "✅ SAFE" if is_safe else "❌ UNSAFE"

        lines.append(f"### {server_name}")
        lines.append("")
        lines.append(f"- **URL:** `{server_url}`")
        lines.append(f"- **Status:** {status}")
        lines.append("")

        # Vulnerability table
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| Critical | {result.get('critical_issues', 0)} |")
        lines.append(f"| High | {result.get('high_severity', 0)} |")
        lines.append(f"| Medium | {result.get('medium_severity', 0)} |")
        lines.append(f"| Low | {result.get('low_severity', 0)} |")
        lines.append("")

        # Show detailed findings for tools with issues
        scan_file = result.get('scan_output_file')
        if scan_file and Path(scan_file).exists():
            try:
                with open(scan_file, 'r') as f:
                    scan_data = json.load(f)

                tool_results = scan_data.get('tool_results', [])
                tools_with_findings = [
                    tool for tool in tool_results
                    if any(
                        finding.get('total_findings', 0) > 0
                        for finding in tool.get('findings', {}).values()
                    )
                ]

                if tools_with_findings:
                    lines.append("#### Detailed Findings")
                    lines.append("")

                    for tool in tools_with_findings:
                        tool_name = tool.get('tool_name', 'Unknown')
                        lines.append(f"**Tool: `{tool_name}`**")
                        lines.append("")

                        # Show findings for each analyzer
                        findings = tool.get('findings', {})
                        for analyzer_name, analyzer_findings in findings.items():
                            total_findings = analyzer_findings.get('total_findings', 0)
                            if total_findings > 0:
                                severity = analyzer_findings.get('severity', 'UNKNOWN')
                                threat_names = analyzer_findings.get('threat_names', [])
                                threat_summary = analyzer_findings.get('threat_summary', '')

                                lines.append(f"- **Analyzer:** {analyzer_name}")
                                lines.append(f"- **Severity:** {severity}")
                                lines.append(f"- **Threats:** {', '.join(threat_names) if threat_names else 'None'}")
                                lines.append(f"- **Summary:** {threat_summary}")

                                # Include taxonomy if available
                                taxonomy = analyzer_findings.get('mcp_taxonomy', {})
                                if taxonomy:
                                    lines.append("")
                                    lines.append("**Taxonomy:**")
                                    lines.append("```json")
                                    lines.append(json.dumps(taxonomy, indent=2))
                                    lines.append("```")

                                lines.append("")

                        # Show tool description if available
                        tool_desc = tool.get('tool_description', '')
                        if tool_desc:
                            lines.append("<details>")
                            lines.append(f"<summary>Tool Description</summary>")
                            lines.append("")
                            lines.append("```")
                            lines.append(tool_desc)
                            lines.append("```")
                            lines.append("</details>")
                            lines.append("")

            except Exception as e:
                logger.warning(f"Could not parse detailed findings from {scan_file}: {e}")
                lines.append(f"**Detailed Report:** [{Path(scan_file).name}]({scan_file})")
                lines.append("")
        else:
            if scan_file:
                lines.append(f"**Detailed Report:** [{Path(scan_file).name}]({scan_file})")
                lines.append("")

        if result.get('error_message'):
            lines.append(f"**Error:** {result['error_message']}")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Report generated on {scan_timestamp}*")
    lines.append("")

    return "\n".join(lines)


def _scan_all_servers(
    base_url: str,
    token_file: Path,
    analyzers: str = DEFAULT_ANALYZERS,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Scan all enabled servers.

    Args:
        base_url: Base URL of the registry
        token_file: Path to token file
        analyzers: Comma-separated list of analyzers
        api_key: Optional API key for LLM analyzer

    Returns:
        Dictionary with scan statistics
    """
    logger.info("=" * 80)
    logger.info("Scan All MCP Servers - Security Vulnerability Scanner")
    logger.info("=" * 80)

    # Load access token from file
    try:
        with open(token_file, 'r') as f:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
            if not access_token:
                raise ValueError(f"No access_token found in {token_file}")
        logger.info(f"Loaded token from: {token_file}")
    except Exception as e:
        logger.error(f"Failed to load token: {e}")
        sys.exit(1)

    # Create registry client
    try:
        client = RegistryClient(
            registry_url=base_url,
            token=access_token
        )
        logger.info(f"Connected to registry at: {base_url}")
    except Exception as e:
        logger.error(f"Failed to create registry client: {e}")
        sys.exit(1)

    # Get server list using the Anthropic Registry API (v0.1)
    try:
        servers_response = client.anthropic_list_servers(limit=1000)
        servers = servers_response.servers if hasattr(servers_response, 'servers') else []
        logger.info(f"Retrieved {len(servers)} servers from registry using Anthropic API v0.1")
    except Exception as e:
        logger.error(f"Failed to get server list: {e}")
        sys.exit(1)

    # Filter enabled servers (using Pydantic attribute access)
    enabled_servers = []
    for server_response in servers:
        # AnthropicServerResponse has a .server attribute of type AnthropicServerDetail
        server = server_response.server

        # Access meta attribute (Optional[Dict[str, Any]])
        # The meta field has alias "_meta" but is accessed via .meta attribute
        if server.meta and "io.mcpgateway/internal" in server.meta:
            internal_meta = server.meta["io.mcpgateway/internal"]
            is_enabled = internal_meta.get("is_enabled", False)

            if is_enabled:
                enabled_servers.append(server)

    logger.info(f"Found {len(enabled_servers)} enabled servers")

    if not enabled_servers:
        logger.warning("No enabled servers found to scan")
        return {"stats": {"total": 0, "passed": 0, "failed": 0}, "scan_results": [], "scan_timestamp": "", "analyzers": analyzers}

    # Scan each server
    stats = {
        "total": len(enabled_servers),
        "passed": 0,
        "failed": 0
    }

    scan_results = []
    scan_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"Scanning {stats['total']} enabled servers")
    logger.info("=" * 80)
    logger.info("")

    # Note: access_token already loaded above for RegistryClient

    for idx, server in enumerate(enabled_servers, 1):
        # Server is AnthropicServerDetail with direct attribute access
        server_name = server.name

        # Get the path from metadata (meta is Optional[Dict])
        server_path = None
        if server.meta and "io.mcpgateway/internal" in server.meta:
            internal_meta = server.meta["io.mcpgateway/internal"]
            server_path = internal_meta.get("path")

        if not server_path:
            logger.warning(f"[{idx}/{stats['total']}] {server_name}: No path found in metadata, skipping")
            stats["failed"] += 1
            scan_results.append({
                "server_name": server_name,
                "server_url": "N/A",
                "success": False,
                "is_safe": False,
                "critical_issues": 0,
                "high_severity": 0,
                "medium_severity": 0,
                "low_severity": 0,
                "error_message": "No path found in metadata"
            })
            continue

        # Construct the gateway proxy URL using the path and base_url
        if not server_path.endswith('/'):
            server_path = server_path + '/'
        server_url = f"{base_url}{server_path}mcp"

        logger.info("-" * 80)
        logger.info(f"[{idx}/{stats['total']}] Scanning: {server_name}")
        logger.info(f"URL: {server_url}")
        logger.info(f"Analyzers: {analyzers}")

        # Run scan with access token for authentication
        scan_result = _run_security_scan(server_url, analyzers, api_key, access_token)
        scan_result["server_name"] = server_name
        scan_result["server_url"] = server_url
        scan_results.append(scan_result)

        if scan_result["success"] and scan_result["is_safe"]:
            stats["passed"] += 1
        else:
            stats["failed"] += 1

        logger.info("")

    return {
        "stats": stats,
        "scan_results": scan_results,
        "scan_timestamp": scan_timestamp,
        "analyzers": analyzers
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scan all enabled MCP servers for security vulnerabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scan all servers with default YARA analyzer
    uv run python cli/scan_all_servers.py

    # Scan with both YARA and LLM analyzers
    export MCP_SCANNER_LLM_API_KEY=sk-your-api-key
    uv run python cli/scan_all_servers.py --analyzers yara,llm

    # Use specific base URL
    uv run python cli/scan_all_servers.py --base-url http://localhost

    # Use custom token file
    uv run python cli/scan_all_servers.py --token-file .oauth-tokens/custom.json

    # Production example
    uv run python cli/scan_all_servers.py \\
        --base-url https://registry.us-east-1.example.com \\
        --token-file api/.token \\
        --analyzers yara,llm
"""
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Registry base URL (default: {DEFAULT_BASE_URL})"
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=DEFAULT_TOKEN_FILE,
        help=f"Path to token file (default: {DEFAULT_TOKEN_FILE})"
    )
    parser.add_argument(
        "--analyzers",
        default=DEFAULT_ANALYZERS,
        help=f"Comma-separated list of analyzers: yara, llm, or yara,llm (default: {DEFAULT_ANALYZERS})"
    )
    parser.add_argument(
        "--api-key",
        help="LLM API key (optional, can also use MCP_SCANNER_LLM_API_KEY env var)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run scans
    results = _scan_all_servers(
        base_url=args.base_url,
        token_file=args.token_file,
        analyzers=args.analyzers,
        api_key=args.api_key
    )

    stats = results["stats"]
    scan_results = results["scan_results"]
    scan_timestamp = results["scan_timestamp"]
    analyzers = results["analyzers"]

    # Generate markdown report
    logger.info("")
    logger.info("=" * 80)
    logger.info("Generating markdown report...")
    logger.info("=" * 80)

    markdown_report = _generate_markdown_report(
        scan_results=scan_results,
        stats=stats,
        analyzers=analyzers,
        scan_timestamp=scan_timestamp
    )

    # Save markdown report
    report_base_dir = PROJECT_ROOT / "security_scans"
    report_base_dir.mkdir(parents=True, exist_ok=True)

    # Create reports subdirectory for timestamped reports
    reports_dir = report_base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Save timestamped report in reports/ subdirectory
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_report = reports_dir / f"scan_report_{timestamp_str}.md"

    with open(timestamped_report, 'w') as f:
        f.write(markdown_report)

    # Save latest report directly in security_scans/
    latest_report = report_base_dir / "scan_report.md"
    with open(latest_report, 'w') as f:
        f.write(markdown_report)

    logger.info(f"Markdown report saved to: {timestamped_report}")
    logger.info(f"Latest report: {latest_report}")

    # Print summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("SCAN SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total servers scanned: {stats['total']}")
    logger.info(f"Passed: {stats['passed']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info("")
    logger.info("Security scan results saved to: ./security_scans/")
    logger.info(f"Markdown report: {latest_report}")
    logger.info("=" * 80)

    # Exit with error code if any scans failed
    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

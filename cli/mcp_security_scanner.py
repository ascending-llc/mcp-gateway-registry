#!/usr/bin/env python3
"""
MCP Security Scanner CLI Tool

Scans MCP servers for security vulnerabilities using cisco-ai-mcp-scanner.
Integrates with service_mgmt.sh to provide security analysis during server registration.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Constants
DEFAULT_ANALYZERS = "yara"
LLM_API_KEY_ENV = "MCP_SCANNER_LLM_API_KEY"
# Use absolute path relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "security_scans"


class SecurityScanResult(BaseModel):
    """Security scan result model."""

    server_url: str = Field(..., description="URL of the scanned MCP server")
    scan_timestamp: str = Field(..., description="ISO timestamp of the scan")
    is_safe: bool = Field(..., description="Overall safety assessment")
    critical_issues: int = Field(default=0, description="Count of critical severity issues")
    high_severity: int = Field(default=0, description="Count of high severity issues")
    medium_severity: int = Field(default=0, description="Count of medium severity issues")
    low_severity: int = Field(default=0, description="Count of low severity issues")
    raw_output: dict = Field(..., description="Full scanner output")
    output_file: str = Field(..., description="Path to detailed JSON output file")


def _get_llm_api_key(
    cli_value: Optional[str] = None
) -> str:
    """Retrieve LLM API key from CLI argument or environment variable.

    Args:
        cli_value: API key provided via command line

    Returns:
        LLM API key for security scanning

    Raises:
        ValueError: If API key is not found
    """
    if cli_value:
        return cli_value

    env_value = os.getenv(LLM_API_KEY_ENV)
    if env_value:
        return env_value

    raise ValueError(
        f"LLM API key must be provided via --api-key or {LLM_API_KEY_ENV} env var"
    )


def _ensure_output_directory() -> Path:
    """Ensure output directory exists."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _run_mcp_scanner(
    server_url: str,
    analyzers: str = DEFAULT_ANALYZERS,
    api_key: Optional[str] = None,
    headers: Optional[str] = None
) -> dict:
    """Run mcp-scanner command and return raw output.

    Args:
        server_url: URL of the MCP server to scan
        analyzers: Comma-separated list of analyzers to use
        api_key: OpenAI API key for LLM-based analysis
        headers: JSON string of headers to include in requests

    Returns:
        Dictionary containing raw scanner output

    Raises:
        subprocess.CalledProcessError: If scanner command fails
    """
    logger.info(f"Running security scan on: {server_url}")
    logger.info(f"Using analyzers: {analyzers}")

    # Build command - global options before subcommand, subcommand options after
    cmd = [
        "mcp-scanner",
        "--analyzers", analyzers,
        "--raw",  # Use raw format instead of summary
        "remote",  # Subcommand to scan remote MCP server
        "--server-url", server_url
    ]

    # Add headers if provided - parse JSON and extract bearer token
    if headers:
        logger.info(f"Adding custom headers for scanning")
        try:
            headers_dict = json.loads(headers)
            # Check for X-Authorization header with Bearer token
            auth_header = headers_dict.get("X-Authorization", "")
            if auth_header.startswith("Bearer "):
                bearer_token = auth_header.replace("Bearer ", "")
                cmd.extend(["--bearer-token", bearer_token])
                logger.info("Using bearer token authentication")
            else:
                logger.warning("Headers provided but no Bearer token found in X-Authorization header")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse headers JSON: {e}")
            raise ValueError(f"Invalid headers JSON: {headers}") from e

    # Set environment variable for API key if provided
    env = os.environ.copy()
    if api_key:
        env[LLM_API_KEY_ENV] = api_key

    # Run scanner
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )

        # Log raw output for debugging
        logger.debug(f"Raw scanner stdout:\n{result.stdout[:500]}")

        # Parse JSON output - scanner outputs JSON array after log messages
        stdout = result.stdout.strip()

        # Remove ANSI color codes that can interfere with JSON parsing
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        stdout = ansi_escape.sub('', stdout)

        # Find the start of JSON array - look for '[\n  {' pattern (array with objects)
        # This is more robust than just finding first '[' or '{'
        json_start = -1

        # Try to find JSON array start
        for i in range(len(stdout) - 1):
            if stdout[i] == '[' and (i == 0 or stdout[i-1] in '\n\r'):
                # Found '[' at start of line, likely start of JSON
                json_start = i
                break

        # Fallback: find any '[' followed by whitespace and '{'
        if json_start == -1:
            pattern = r'\[\s*\{'
            match = re.search(pattern, stdout)
            if match:
                json_start = match.start()

        if json_start == -1:
            raise ValueError("No JSON array found in scanner output")

        # Extract and parse JSON
        json_str = stdout[json_start:]
        tool_results = json.loads(json_str)

        # Wrap in expected format with analysis_results
        # Convert array of tool results to the expected structure
        raw_output = {
            "analysis_results": {},
            "tool_results": tool_results
        }

        # Extract findings from tool results and organize by analyzer
        for tool_result in tool_results:
            findings_dict = tool_result.get("findings", {})
            for analyzer_name, analyzer_findings in findings_dict.items():
                if analyzer_name not in raw_output["analysis_results"]:
                    raw_output["analysis_results"][analyzer_name] = {"findings": []}

                # Convert analyzer findings to expected format
                if isinstance(analyzer_findings, dict):
                    finding = {
                        "tool_name": tool_result.get("tool_name"),
                        "severity": analyzer_findings.get("severity", "unknown"),
                        "threat_names": analyzer_findings.get("threat_names", []),
                        "threat_summary": analyzer_findings.get("threat_summary", ""),
                        "is_safe": tool_result.get("is_safe", True)
                    }
                    raw_output["analysis_results"][analyzer_name]["findings"].append(finding)

        logger.debug(f"Scanner output:\n{json.dumps(raw_output, indent=2, default=str)}")
        return raw_output

    except subprocess.CalledProcessError as e:
        logger.error(f"Scanner command failed with exit code {e.returncode}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse scanner output as JSON: {e}")
        logger.error(f"Raw stdout: {result.stdout[:1000]}")
        raise


def _analyze_scan_results(
    raw_output: dict
) -> tuple[bool, int, int, int, int]:
    """Analyze scan results and extract severity counts.

    Args:
        raw_output: Raw scanner output dictionary

    Returns:
        Tuple of (is_safe, critical_count, high_count, medium_count, low_count)
    """
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0

    # Navigate the raw output structure to find findings
    # Structure: raw_output -> analysis_results -> [analyzer_name] -> findings
    analysis_results = raw_output.get("analysis_results", {})

    for _analyzer_name, analyzer_data in analysis_results.items():
        if isinstance(analyzer_data, dict):
            findings = analyzer_data.get("findings", [])
            for finding in findings:
                severity = finding.get("severity", "").lower()
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1
                elif severity == "medium":
                    medium_count += 1
                elif severity == "low":
                    low_count += 1

    # Determine if safe: no critical or high severity issues
    is_safe = (critical_count == 0 and high_count == 0)

    logger.info(f"Security analysis results:")
    logger.info(f"  Critical Issues: {critical_count}")
    logger.info(f"  High Severity: {high_count}")
    logger.info(f"  Medium Severity: {medium_count}")
    logger.info(f"  Low Severity: {low_count}")
    logger.info(f"  Overall Assessment: {'SAFE' if is_safe else 'UNSAFE'}")

    return is_safe, critical_count, high_count, medium_count, low_count


def _save_scan_output(
    server_url: str,
    raw_output: dict
) -> str:
    """Save detailed scan output to JSON file.

    Saves in two locations:
    1. security_scans/YYYY-MM-DD/scan_<server>_<timestamp>.json (archived)
    2. security_scans/scan_<server>_latest.json (always current)

    Args:
        server_url: URL of the scanned server
        raw_output: Raw scanner output

    Returns:
        Path to saved output file (latest version)
    """
    output_dir = _ensure_output_directory()

    # Generate safe filename from server URL
    safe_url = server_url.replace("https://", "").replace("http://", "").replace("/", "_")

    # Create date-based subdirectory for archival
    timestamp = datetime.now(timezone.utc)
    date_folder = timestamp.strftime("%Y-%m-%d")
    archive_dir = output_dir / date_folder
    archive_dir.mkdir(exist_ok=True)

    # Save timestamped version in date folder (archived)
    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
    archived_filename = f"scan_{safe_url}_{timestamp_str}.json"
    archived_file = archive_dir / archived_filename

    with open(archived_file, 'w') as f:
        json.dump(raw_output, f, indent=2, default=str)

    logger.info(f"Archived scan output saved to: {archived_file}")

    # Save latest version in root security_scans folder (always current)
    # Extract server name from URL for cleaner filename
    # e.g., http://localhost/realserverfaketools/mcp -> realserverfaketools_mcp.json
    server_name = safe_url.replace("localhost_", "")
    latest_filename = f"{server_name}.json"
    latest_file = output_dir / latest_filename

    with open(latest_file, 'w') as f:
        json.dump(raw_output, f, indent=2, default=str)

    logger.info(f"Latest scan output saved to: {latest_file}")

    return str(latest_file)


def _disable_unsafe_server(
    server_path: str
) -> bool:
    """Disable a server that failed security scan.

    Args:
        server_path: Path of the server to disable (e.g., /mcpgw)

    Returns:
        True if server was disabled successfully, False otherwise
    """
    logger.info(f"Disabling unsafe server: {server_path}")

    try:
        # Call service_mgmt.sh to disable the server
        cmd = [
            str(PROJECT_ROOT / "cli" / "service_mgmt.sh"),
            "disable",
            server_path
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        logger.info(f"Server {server_path} disabled successfully")
        logger.debug(f"Output: {result.stdout}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to disable server {server_path}: {e}")
        logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error disabling server {server_path}: {e}")
        return False


def _extract_server_path_from_url(
    server_url: str
) -> Optional[str]:
    """Extract server path from URL.

    Args:
        server_url: Full server URL (e.g., http://localhost/mcpgw/mcp)

    Returns:
        Server path (e.g., /mcpgw) or None if cannot be extracted
    """
    try:
        # Parse URL to extract path component
        # Expected format: http://localhost/server-path/mcp
        from urllib.parse import urlparse

        parsed = urlparse(server_url)
        path_parts = [p for p in parsed.path.split('/') if p and p != 'mcp']

        if path_parts:
            server_path = f"/{path_parts[0]}"
            logger.debug(f"Extracted server path '{server_path}' from URL '{server_url}'")
            return server_path
        else:
            logger.warning(f"Could not extract server path from URL: {server_url}")
            return None

    except Exception as e:
        logger.error(f"Error parsing server URL {server_url}: {e}")
        return None


def scan_server(
    server_url: str,
    analyzers: str = DEFAULT_ANALYZERS,
    api_key: Optional[str] = None,
    output_json: bool = False,
    auto_disable: bool = False,
    headers: Optional[str] = None
) -> SecurityScanResult:
    """Scan an MCP server for security vulnerabilities.

    Args:
        server_url: URL of the MCP server to scan
        analyzers: Comma-separated list of analyzers to use
        api_key: OpenAI API key for LLM-based analysis
        output_json: If True, output raw mcp-scanner JSON directly
        auto_disable: If True, automatically disable servers that fail security scan
        headers: JSON string of headers to include in requests

    Returns:
        SecurityScanResult containing scan results
    """
    # Run scanner
    try:
        raw_output = _run_mcp_scanner(server_url, analyzers, api_key, headers)
    except subprocess.CalledProcessError as e:
        # Scanner failed - create error output and save it
        logger.error(f"Scanner failed with exit code {e.returncode}")
        raw_output = {
            "error": str(e),
            "stderr": e.stderr if hasattr(e, 'stderr') else "",
            "analysis_results": {},
            "tool_results": [],
            "scan_failed": True
        }
        # Save the error output
        output_file = _save_scan_output(server_url, raw_output)

        # Create error result
        result = SecurityScanResult(
            server_url=server_url,
            scan_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            is_safe=False,  # Treat scanner failures as unsafe
            critical_issues=0,
            high_severity=0,
            medium_severity=0,
            low_severity=0,
            raw_output=raw_output,
            output_file=output_file
        )

        # Output result
        if output_json:
            print(json.dumps(result.model_dump(), indent=2, default=str))
        else:
            print("\n" + "="*60)
            print("SECURITY SCAN FAILED")
            print("="*60)
            print(f"Server URL: {result.server_url}")
            print(f"Scan Time: {result.scan_timestamp}")
            print(f"\nError: Scanner failed to complete scan")
            print(f"Details: {e}")
            print(f"\nMarking server as UNSAFE due to scanner failure")
            print(f"\nDetailed output saved to: {result.output_file}")
            print("="*60 + "\n")

        return result

    # Analyze results
    is_safe, critical, high, medium, low = _analyze_scan_results(raw_output)

    # Save detailed output
    output_file = _save_scan_output(server_url, raw_output)

    # Auto-disable server if unsafe
    if auto_disable and not is_safe:
        logger.warning(f"Server marked as UNSAFE - attempting to disable")
        server_path = _extract_server_path_from_url(server_url)
        if server_path:
            if _disable_unsafe_server(server_path):
                logger.info(f"✓ Server {server_path} has been disabled for security reasons")
            else:
                logger.error(f"✗ Failed to disable server {server_path}")
        else:
            logger.error(f"✗ Could not extract server path from URL - manual intervention required")

    # Create result object
    result = SecurityScanResult(
        server_url=server_url,
        scan_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        is_safe=is_safe,
        critical_issues=critical,
        high_severity=high,
        medium_severity=medium,
        low_severity=low,
        raw_output=raw_output,
        output_file=output_file
    )

    # Output result
    if output_json:
        # Output raw mcp-scanner format directly (same as --raw)
        print(json.dumps(raw_output, indent=2, default=str))
    else:
        print("\n" + "="*60)
        print("SECURITY SCAN SUMMARY")
        print("="*60)
        print(f"Server URL: {result.server_url}")
        print(f"Scan Time: {result.scan_timestamp}")
        print(f"\nEXECUTIVE SUMMARY OF ISSUES:")
        print(f"  Critical Issues: {result.critical_issues}")
        print(f"  High Severity: {result.high_severity}")
        print(f"  Medium Severity: {result.medium_severity}")
        print(f"  Low Severity: {result.low_severity}")
        print(f"\nOverall Assessment: {'SAFE ✓' if result.is_safe else 'UNSAFE ✗'}")

        # Show auto-disable status if applicable
        if auto_disable and not result.is_safe:
            server_path = _extract_server_path_from_url(server_url)
            if server_path:
                print(f"\n⚠️  ACTION TAKEN: Server {server_path} has been DISABLED due to security issues")
            else:
                print(f"\n⚠️  WARNING: Could not auto-disable server - manual intervention required")

        print(f"\nDetailed output saved to: {result.output_file}")
        print("="*60 + "\n")

    return result


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Scan MCP servers for security vulnerabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
    # Basic scan with YARA analyzer (default)
    uv run cli/mcp_security_scanner.py --server-url https://mcp.deepwki.com/mcp

    # Scan with both YARA and LLM analyzers
    export MCP_SCANNER_LLM_API_KEY=sk-...
    uv run cli/mcp_security_scanner.py --server-url https://example.com/mcp --analyzers yara,llm

    # Scan with LLM only, passing API key directly
    uv run cli/mcp_security_scanner.py --server-url https://example.com/mcp --analyzers llm --api-key sk-...

    # Scan with custom headers (e.g., authentication)
    uv run cli/mcp_security_scanner.py --server-url https://example.com/mcp --headers '{"X-Authorization": "Bearer token123"}'

    # Output as JSON
    uv run cli/mcp_security_scanner.py --server-url https://example.com/mcp --json
"""
    )

    parser.add_argument(
        "--server-url",
        required=True,
        help="URL of the MCP server to scan"
    )

    parser.add_argument(
        "--analyzers",
        default=DEFAULT_ANALYZERS,
        help=f"Comma-separated list of analyzers to use (default: {DEFAULT_ANALYZERS})"
    )

    parser.add_argument(
        "--api-key",
        help=f"LLM API key for security scanning (can also use {LLM_API_KEY_ENV} env var)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    parser.add_argument(
        "--auto-disable",
        action="store_true",
        help="Automatically disable servers that fail security scan (is_safe: false)"
    )

    parser.add_argument(
        "--headers",
        help="JSON string of headers to include in requests (e.g., '{\"X-Authorization\": \"token\"}')"
    )

    args = parser.parse_args()

    # Set debug level if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Get API key if needed for LLM analyzer
        api_key = None
        if "llm" in args.analyzers.lower():
            api_key = _get_llm_api_key(args.api_key)

        # Run scan
        result = scan_server(
            server_url=args.server_url,
            analyzers=args.analyzers,
            api_key=api_key,
            output_json=args.json,
            auto_disable=args.auto_disable,
            headers=args.headers
        )

        # Exit with non-zero code if unsafe
        sys.exit(0 if result.is_safe else 1)

    except Exception as e:
        logger.exception(f"Security scan failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()

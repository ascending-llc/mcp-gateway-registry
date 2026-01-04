"""
Security schema models for MCP server scanning.

This module defines Pydantic models for security scan results, configurations,
and related data structures used throughout the security scanning workflow.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SecurityScanFinding(BaseModel):
    """Individual security finding from a scanner."""

    tool_name: str = Field(..., description="Name of the tool that was scanned")
    severity: str = Field(..., description="Severity level: CRITICAL, HIGH, MEDIUM, LOW, SAFE")
    threat_names: list[str] = Field(default_factory=list, description="List of detected threat names")
    threat_summary: str = Field(default="", description="Summary of threats found")
    is_safe: bool = Field(..., description="Whether the tool is considered safe")


class SecurityScanAnalyzerResult(BaseModel):
    """Results from a specific security analyzer."""

    analyzer_name: str = Field(..., description="Name of the analyzer (yara, llm, etc.)")
    findings: list[SecurityScanFinding] = Field(default_factory=list, description="List of findings from this analyzer")


class SecurityScanResult(BaseModel):
    """Complete security scan result for an MCP server."""

    server_url: str = Field(..., description="URL of the scanned MCP server")
    scan_timestamp: str = Field(..., description="ISO timestamp of the scan")
    is_safe: bool = Field(..., description="Overall safety assessment")
    critical_issues: int = Field(default=0, description="Count of critical severity issues")
    high_severity: int = Field(default=0, description="Count of high severity issues")
    medium_severity: int = Field(default=0, description="Count of medium severity issues")
    low_severity: int = Field(default=0, description="Count of low severity issues")
    analyzers_used: list[str] = Field(default_factory=list, description="List of analyzers used in scan")
    raw_output: dict = Field(default_factory=dict, description="Full scanner output")
    output_file: Optional[str] = Field(None, description="Path to detailed JSON output file")
    scan_failed: bool = Field(default=False, description="Whether the scan failed to complete")
    error_message: Optional[str] = Field(None, description="Error message if scan failed")


class SecurityScanConfig(BaseModel):
    """Configuration for security scanning."""

    enabled: bool = Field(default=True, description="Enable/disable security scanning")
    scan_on_registration: bool = Field(default=True, description="Scan servers during registration")
    block_unsafe_servers: bool = Field(default=True, description="Disable servers that fail security scan")
    analyzers: str = Field(default="yara", description="Comma-separated list of analyzers to use")
    scan_timeout_seconds: int = Field(default=300, description="Timeout for security scans in seconds")
    llm_api_key: Optional[str] = Field(None, description="API key for LLM-based analysis")
    add_security_pending_tag: bool = Field(default=True, description="Add 'security-pending' tag to unsafe servers")


class ServerSecurityStatus(BaseModel):
    """Security status summary for a server."""

    server_path: str = Field(..., description="Server path (e.g., /mcpgw)")
    server_name: str = Field(..., description="Display name of the server")
    is_safe: bool = Field(..., description="Whether the server passed security scan")
    last_scan_timestamp: Optional[str] = Field(None, description="ISO timestamp of last scan")
    critical_issues: int = Field(default=0, description="Count of critical issues")
    high_severity: int = Field(default=0, description="Count of high severity issues")
    scan_status: str = Field(default="pending", description="Status: pending, completed, failed")
    is_disabled_for_security: bool = Field(default=False, description="Whether server is disabled due to security issues")

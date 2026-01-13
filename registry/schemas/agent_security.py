"""
Agent security schema models for A2A scanner integration.

This module defines Pydantic models for agent security scan results, configurations,
and related data structures used throughout the A2A security scanning workflow.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AgentSecurityScanFinding(BaseModel):
    """Individual security finding from A2A scanner."""

    skill_name: Optional[str] = Field(None, description="Name of the skill that was scanned (if applicable)")
    agent_component: str = Field("agent_card", description="Component scanned: agent_card, skill, endpoint")
    severity: str = Field(..., description="Severity level: CRITICAL, HIGH, MEDIUM, LOW, SAFE")
    threat_names: list[str] = Field(default_factory=list, description="List of detected threat names")
    threat_summary: str = Field(default="", description="Summary of threats found")
    is_safe: bool = Field(..., description="Whether the component is considered safe")


class AgentSecurityScanAnalyzerResult(BaseModel):
    """Results from a specific A2A security analyzer."""

    analyzer_name: str = Field(..., description="Name of the analyzer (yara, spec, heuristic, llm, endpoint)")
    findings: list[AgentSecurityScanFinding] = Field(default_factory=list, description="List of findings from this analyzer")


class AgentSecurityScanResult(BaseModel):
    """Complete security scan result for an A2A agent."""

    agent_path: str = Field(..., description="Path of the scanned agent")
    agent_url: Optional[str] = Field(None, description="URL of the scanned agent endpoint")
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


class AgentSecurityScanConfig(BaseModel):
    """Configuration for A2A agent security scanning."""

    enabled: bool = Field(default=True, description="Enable/disable agent security scanning")
    scan_on_registration: bool = Field(default=True, description="Scan agents during registration")
    block_unsafe_agents: bool = Field(default=True, description="Disable agents that fail security scan")
    analyzers: str = Field(default="yara,spec", description="Comma-separated list of analyzers to use")
    scan_timeout_seconds: int = Field(default=300, description="Timeout for security scans in seconds")
    llm_api_key: Optional[str] = Field(None, description="API key for LLM-based analysis")
    add_security_pending_tag: bool = Field(default=True, description="Add 'security-pending' tag to unsafe agents")


class AgentSecurityStatus(BaseModel):
    """Security status summary for an agent."""

    agent_path: str = Field(..., description="Agent path (e.g., /code-reviewer)")
    agent_name: str = Field(..., description="Display name of the agent")
    is_safe: bool = Field(..., description="Whether the agent passed security scan")
    last_scan_timestamp: Optional[str] = Field(None, description="ISO timestamp of last scan")
    critical_issues: int = Field(default=0, description="Count of critical issues")
    high_severity: int = Field(default=0, description="Count of high severity issues")
    scan_status: str = Field(default="pending", description="Status: pending, completed, failed")
    is_disabled_for_security: bool = Field(default=False, description="Whether agent is disabled due to security issues")

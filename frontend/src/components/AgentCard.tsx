import React, { useState, useCallback } from 'react';
import axios from 'axios';
import {
  CpuChipIcon,
  StarIcon,
  ArrowPathIcon,
  PencilIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  QuestionMarkCircleIcon,
  ClipboardDocumentIcon,
  ShieldCheckIcon,
  GlobeAltIcon,
  LockClosedIcon,
  InformationCircleIcon
} from '@heroicons/react/24/outline';

/**
 * Agent interface representing an A2A agent.
 */
interface Agent {
  name: string;
  path: string;
  description?: string;
  version?: string;
  visibility?: 'public' | 'private';
  trust_level?: 'community' | 'verified' | 'trusted';
  enabled: boolean;
  tags?: string[];
  last_checked_time?: string;
  usersCount?: number;
  rating?: number;
  status?: 'healthy' | 'healthy-auth-expired' | 'unhealthy' | 'unknown';
}

/**
 * Props for the AgentCard component.
 */
interface AgentCardProps {
  agent: Agent & { [key: string]: any };  // Allow additional fields from full agent JSON
  onToggle: (path: string, enabled: boolean) => void;
  onEdit?: (agent: Agent) => void;
  canModify?: boolean;
  onRefreshSuccess?: () => void;
  onShowToast?: (message: string, type: 'success' | 'error') => void;
  onAgentUpdate?: (path: string, updates: Partial<Agent>) => void;
}

/**
 * Helper function to format time since last checked.
 */
const formatTimeSince = (timestamp: string | null | undefined): string | null => {
  if (!timestamp) {
    console.log('formatTimeSince: No timestamp provided', timestamp);
    return null;
  }

  try {
    const now = new Date();
    const lastChecked = new Date(timestamp);

    // Check if the date is valid
    if (isNaN(lastChecked.getTime())) {
      console.log('formatTimeSince: Invalid timestamp', timestamp);
      return null;
    }

    const diffMs = now.getTime() - lastChecked.getTime();

    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    let result;
    if (diffDays > 0) {
      result = `${diffDays}d ago`;
    } else if (diffHours > 0) {
      result = `${diffHours}h ago`;
    } else if (diffMinutes > 0) {
      result = `${diffMinutes}m ago`;
    } else {
      result = `${diffSeconds}s ago`;
    }

    console.log(`formatTimeSince: ${timestamp} -> ${result}`);
    return result;
  } catch (error) {
    console.error('formatTimeSince error:', error, 'for timestamp:', timestamp);
    return null;
  }
};

/**
 * AgentCard component for displaying A2A agents.
 *
 * Displays agent information with a distinct visual style from MCP servers,
 * using blue/cyan tones and robot-themed icons.
 */
const AgentCard: React.FC<AgentCardProps> = ({
  agent,
  onToggle,
  onEdit,
  canModify,
  onRefreshSuccess,
  onShowToast,
  onAgentUpdate
}) => {
  const [showConfig, setShowConfig] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [selectedIDE, setSelectedIDE] = useState<'vscode' | 'cursor' | 'cline' | 'claude-code'>('vscode');
  const [loadingRefresh, setLoadingRefresh] = useState(false);
  const [fullAgentDetails, setFullAgentDetails] = useState<any>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [selectedCliCommand, setSelectedCliCommand] = useState<'register' | 'list' | 'get' | 'test' | 'test-all' | 'search' | 'update' | 'toggle' | 'delete'>('list');

  const getStatusIcon = () => {
    switch (agent.status) {
      case 'healthy':
        return <CheckCircleIcon className="h-4 w-4 text-green-500" />;
      case 'healthy-auth-expired':
        return <CheckCircleIcon className="h-4 w-4 text-orange-500" />;
      case 'unhealthy':
        return <XCircleIcon className="h-4 w-4 text-red-500" />;
      default:
        return <QuestionMarkCircleIcon className="h-4 w-4 text-gray-400" />;
    }
  };

  const getTrustLevelColor = () => {
    switch (agent.trust_level) {
      case 'trusted':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-700';
      case 'verified':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-700';
      case 'community':
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600';
    }
  };

  const getTrustLevelIcon = () => {
    switch (agent.trust_level) {
      case 'trusted':
        return <ShieldCheckIcon className="h-3 w-3" />;
      case 'verified':
        return <CheckCircleIcon className="h-3 w-3" />;
      default:
        return null;
    }
  };

  const getVisibilityIcon = () => {
    return agent.visibility === 'public' ? (
      <GlobeAltIcon className="h-3 w-3" />
    ) : (
      <LockClosedIcon className="h-3 w-3" />
    );
  };

  const handleRefreshHealth = useCallback(async () => {
    if (loadingRefresh) return;

    setLoadingRefresh(true);
    try {
      // Extract agent name from path (remove leading slash)
      const agentName = agent.path.replace(/^\//, '');

      const response = await axios.post(`/api/refresh/${agentName}`);

      // Update just this agent instead of triggering global refresh
      if (onAgentUpdate && response.data) {
        const updates: Partial<Agent> = {
          status: response.data.status === 'healthy' ? 'healthy' :
                  response.data.status === 'healthy-auth-expired' ? 'healthy-auth-expired' :
                  response.data.status === 'unhealthy' ? 'unhealthy' : 'unknown',
          last_checked_time: response.data.last_checked_iso
        };

        onAgentUpdate(agent.path, updates);
      } else if (onRefreshSuccess) {
        // Fallback to global refresh if onAgentUpdate is not provided
        onRefreshSuccess();
      }

      if (onShowToast) {
        onShowToast('Agent health status refreshed successfully', 'success');
      }
    } catch (error: any) {
      console.error('Failed to refresh agent health:', error);
      if (onShowToast) {
        onShowToast(error.response?.data?.detail || 'Failed to refresh agent health status', 'error');
      }
    } finally {
      setLoadingRefresh(false);
    }
  }, [agent.path, loadingRefresh, onRefreshSuccess, onShowToast, onAgentUpdate]);

  /**
   * Generate CLI command for agent management.
   */
  const generateCliCommand = useCallback((): string => {
    const agentPath = agent.path;
    const agentName = agent.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');

    switch (selectedCliCommand) {
      case 'list':
        return 'uv run python cli/agent_mgmt.py list';

      case 'get':
        return `uv run python cli/agent_mgmt.py get ${agentPath}`;

      case 'test':
        return `uv run python cli/agent_mgmt.py test ${agentPath}`;

      case 'test-all':
        return 'uv run python cli/agent_mgmt.py test-all';

      case 'search':
        return `uv run python cli/agent_mgmt.py search "${agent.name}"`;

      case 'update':
        return `uv run python cli/agent_mgmt.py update ${agentPath} cli/examples/${agentName}_agent.json`;

      case 'toggle':
        return `uv run python cli/agent_mgmt.py toggle ${agentPath} true   # Enable\nuv run python cli/agent_mgmt.py toggle ${agentPath} false  # Disable`;

      case 'delete':
        return `uv run python cli/agent_mgmt.py delete ${agentPath}`;

      case 'register':
      default:
        return `uv run python cli/agent_mgmt.py register cli/examples/${agentName}_agent.json`;
    }
  }, [selectedCliCommand, agent.path, agent.name]);

  /**
   * Get description for the selected CLI command.
   */
  const getCliCommandDescription = useCallback((): string => {
    switch (selectedCliCommand) {
      case 'list':
        return 'List all agents (filtered by your permissions). Shows agent summaries with basic metadata.';

      case 'get':
        return 'Retrieve the complete agent card for a specific agent, including all metadata, skills, and configuration.';

      case 'test':
        return 'Verify agent registration in registry and test endpoint accessibility. Checks health status.';

      case 'test-all':
        return 'Test all registered agents to verify they are accessible and healthy.';

      case 'search':
        return 'Perform semantic search to find agents by capability. Searches by name, description, and tags.';

      case 'update':
        return 'Update an agent\'s metadata and configuration. Requires the agent JSON file with updated values.';

      case 'toggle':
        return 'Enable or disable an agent in the registry without deleting it. Useful for maintenance.';

      case 'delete':
        return 'Remove an agent from the registry. This action is permanent.';

      case 'register':
      default:
        return 'Register a new agent with the registry. Requires a properly formatted agent JSON file with metadata, skills, and security schemes.';
    }
  }, [selectedCliCommand]);

  /**
   * Generate agent configuration for discovery/information.
   */
  const generateAgentConfig = useCallback(() => {
    const agentName = agent.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');

    // Get base URL and strip port for nginx proxy compatibility
    const currentUrl = new URL(window.location.origin);
    const baseUrl = `${currentUrl.protocol}//${currentUrl.hostname}`;

    // Clean up agent path - remove trailing slashes and ensure single leading slash
    const cleanPath = agent.path.replace(/\/+$/, '').replace(/^\/+/, '/');
    const url = `${baseUrl}${cleanPath}/a2a`;

    // Generate different config formats for different IDEs
    switch(selectedIDE) {
      case 'vscode':
        return {
          "agents": {
            [agentName]: {
              "type": "a2a",
              "url": url,
              "version": agent.version || "1.0.0",
              "trust_level": agent.trust_level || "community",
              "headers": {
                "Authorization": "Bearer [YOUR_AUTH_TOKEN]"
              }
            }
          },
          "inputs": [
            {
              "type": "promptString",
              "id": "auth-token",
              "description": "Gateway Authentication Token"
            }
          ]
        };

      case 'cursor':
        return {
          "a2aAgents": {
            [agentName]: {
              "url": url,
              "version": agent.version || "1.0.0",
              "trust_level": agent.trust_level || "community",
              "headers": {
                "Authorization": "Bearer [YOUR_AUTH_TOKEN]"
              }
            }
          }
        };

      case 'cline':
        return {
          "a2aAgents": {
            [agentName]: {
              "type": "a2a",
              "url": url,
              "version": agent.version || "1.0.0",
              "trust_level": agent.trust_level || "community",
              "disabled": false,
              "headers": {
                "Authorization": "Bearer [YOUR_AUTH_TOKEN]"
              }
            }
          }
        };

      case 'claude-code':
        return {
          "a2aAgents": {
            [agentName]: {
              "type": "a2a",
              "url": url,
              "version": agent.version || "1.0.0",
              "trust_level": agent.trust_level || "community",
              "headers": {
                "Authorization": "Bearer [YOUR_AUTH_TOKEN]"
              }
            }
          }
        };

      default:
        return {
          "a2aAgents": {
            [agentName]: {
              "type": "a2a",
              "url": url,
              "version": agent.version || "1.0.0",
              "trust_level": agent.trust_level || "community",
              "headers": {
                "Authorization": "Bearer [YOUR_AUTH_TOKEN]"
              }
            }
          }
        };
    }
  }, [agent.name, agent.path, agent.version, agent.trust_level, selectedIDE]);

  /**
   * Copy configuration to clipboard.
   */
  const copyConfigToClipboard = useCallback(async () => {
    try {
      const config = generateAgentConfig();
      const configText = JSON.stringify(config, null, 2);
      await navigator.clipboard.writeText(configText);

      if (onShowToast) {
        onShowToast('Agent configuration copied to clipboard!', 'success');
      }
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      if (onShowToast) {
        onShowToast('Failed to copy configuration', 'error');
      }
    }
  }, [generateAgentConfig, onShowToast]);

  /**
   * Copy CLI command to clipboard.
   */
  const copyCliCommandToClipboard = useCallback(async () => {
    try {
      const command = generateCliCommand();
      await navigator.clipboard.writeText(command);

      if (onShowToast) {
        onShowToast('CLI command copied to clipboard!', 'success');
      }
    } catch (error) {
      console.error('Failed to copy CLI command:', error);
      if (onShowToast) {
        onShowToast('Failed to copy CLI command', 'error');
      }
    }
  }, [generateCliCommand, onShowToast]);

  return (
    <>
      <div className="group rounded-2xl shadow-sm hover:shadow-xl transition-all duration-300 h-full flex flex-col bg-gradient-to-br from-cyan-50 to-blue-50 dark:from-cyan-900/20 dark:to-blue-900/20 border-2 border-cyan-200 dark:border-cyan-700 hover:border-cyan-300 dark:hover:border-cyan-600">
        {/* Header */}
        <div className="p-5 pb-4">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-3">
                <h3 className="text-lg font-bold text-gray-900 dark:text-white truncate">
                  {agent.name}
                </h3>
                <span className="px-2 py-0.5 text-xs font-semibold bg-gradient-to-r from-cyan-100 to-blue-100 text-cyan-700 dark:from-cyan-900/30 dark:to-blue-900/30 dark:text-cyan-300 rounded-full flex-shrink-0 border border-cyan-200 dark:border-cyan-600">
                  AGENT
                </span>
                {agent.trust_level && (
                  <span className={`px-2 py-0.5 text-xs font-semibold rounded-full flex-shrink-0 flex items-center gap-1 ${getTrustLevelColor()}`}>
                    {getTrustLevelIcon()}
                    {agent.trust_level.toUpperCase()}
                  </span>
                )}
                {agent.visibility && (
                  <span className={`px-2 py-0.5 text-xs font-semibold rounded-full flex-shrink-0 flex items-center gap-1 ${
                    agent.visibility === 'public'
                      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-700'
                      : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600'
                  }`}>
                    {getVisibilityIcon()}
                    {agent.visibility.toUpperCase()}
                  </span>
                )}
              </div>

              <code className="text-xs text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/50 px-2 py-1 rounded font-mono">
                {agent.path}
              </code>
              {agent.version && (
                <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                  v{agent.version}
                </span>
              )}
            </div>

            {canModify && (
              <button
                className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-lg transition-all duration-200 flex-shrink-0"
                onClick={() => onEdit?.(agent)}
                title="Edit agent"
              >
                <PencilIcon className="h-4 w-4" />
              </button>
            )}

            {/* Full Details Button */}
            <button
              onClick={async () => {
                setShowDetails(true);
                setLoadingDetails(true);
                try {
                  const response = await axios.get(`/api/agents${agent.path}`);
                  setFullAgentDetails(response.data);
                } catch (error) {
                  console.error('Failed to fetch agent details:', error);
                  if (onShowToast) {
                    onShowToast('Failed to load full agent details', 'error');
                  }
                } finally {
                  setLoadingDetails(false);
                }
              }}
              className="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-700/50 rounded-lg transition-all duration-200 flex-shrink-0"
              title="View full agent details (JSON)"
            >
              <InformationCircleIcon className="h-4 w-4" />
            </button>
          </div>

          {/* Description */}
          <p className="text-gray-600 dark:text-gray-300 text-sm leading-relaxed line-clamp-2 mb-4">
            {agent.description || 'No description available'}
          </p>

          {/* Tags */}
          {agent.tags && agent.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-4">
              {agent.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-1 text-xs font-medium bg-cyan-50 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300 rounded"
                >
                  #{tag}
                </span>
              ))}
              {agent.tags.length > 3 && (
                <span className="px-2 py-1 text-xs font-medium bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded">
                  +{agent.tags.length - 3}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="px-5 pb-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-yellow-50 dark:bg-yellow-900/30 rounded">
                <StarIcon className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
              </div>
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">{agent.rating || 0}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Rating</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-cyan-50 dark:bg-cyan-900/30 rounded">
                <CpuChipIcon className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
              </div>
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">{agent.usersCount || 0}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Users</div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-auto px-5 py-4 border-t border-cyan-100 dark:border-cyan-700 bg-cyan-50/50 dark:bg-cyan-900/30 rounded-b-2xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* Status Indicators */}
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${
                  agent.enabled
                    ? 'bg-green-400 shadow-lg shadow-green-400/30'
                    : 'bg-gray-300 dark:bg-gray-600'
                }`} />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {agent.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>

              <div className="w-px h-4 bg-cyan-200 dark:bg-cyan-600" />

              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${
                  agent.status === 'healthy'
                    ? 'bg-emerald-400 shadow-lg shadow-emerald-400/30'
                    : agent.status === 'healthy-auth-expired'
                    ? 'bg-orange-400 shadow-lg shadow-orange-400/30'
                    : agent.status === 'unhealthy'
                    ? 'bg-red-400 shadow-lg shadow-red-400/30'
                    : 'bg-amber-400 shadow-lg shadow-amber-400/30'
                }`} />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {agent.status === 'healthy' ? 'Healthy' :
                   agent.status === 'healthy-auth-expired' ? 'Healthy (Auth Expired)' :
                   agent.status === 'unhealthy' ? 'Unhealthy' : 'Unknown'}
                </span>
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-3">
              {/* Last Checked */}
              {(() => {
                console.log(`AgentCard ${agent.name}: last_checked_time =`, agent.last_checked_time);
                const timeText = formatTimeSince(agent.last_checked_time);
                console.log(`AgentCard ${agent.name}: timeText =`, timeText);
                return agent.last_checked_time && timeText ? (
                  <div className="text-xs text-gray-500 dark:text-gray-300 flex items-center gap-1.5">
                    <ClockIcon className="h-3.5 w-3.5" />
                    <span>{timeText}</span>
                  </div>
                ) : null;
              })()}

              {/* Refresh Button */}
              <button
                onClick={handleRefreshHealth}
                disabled={loadingRefresh}
                className="p-2.5 text-gray-500 hover:text-cyan-600 dark:hover:text-cyan-400 hover:bg-cyan-50 dark:hover:bg-cyan-900/20 rounded-lg transition-all duration-200 disabled:opacity-50"
                title="Refresh agent health status"
              >
                <ArrowPathIcon className={`h-4 w-4 ${loadingRefresh ? 'animate-spin' : ''}`} />
              </button>

              {/* Toggle Switch */}
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={agent.enabled}
                  onChange={(e) => onToggle(agent.path, e.target.checked)}
                  className="sr-only peer"
                />
                <div className={`relative w-12 h-6 rounded-full transition-colors duration-200 ease-in-out ${
                  agent.enabled
                    ? 'bg-cyan-600'
                    : 'bg-gray-300 dark:bg-gray-600'
                }`}>
                  <div className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform duration-200 ease-in-out ${
                    agent.enabled ? 'translate-x-6' : 'translate-x-0'
                  }`} />
                </div>
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Full Details Modal */}
      {showDetails && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 max-w-4xl w-full mx-4 max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {agent.name} - Full Details (JSON)
              </h3>
              <button
                onClick={() => setShowDetails(false)}
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              {/* Info Note */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h4 className="font-medium text-blue-900 dark:text-blue-100 mb-2">
                  Complete Agent Schema
                </h4>
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  This is the complete A2A agent definition stored in the registry. It includes all metadata, skills, security schemes, and configuration details.
                </p>
              </div>

              {/* Full JSON */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium text-gray-900 dark:text-white">
                    Agent JSON Schema:
                  </h4>
                  <button
                    onClick={() => {
                      try {
                        const dataToCopy = fullAgentDetails || agent;
                        navigator.clipboard.writeText(JSON.stringify(dataToCopy, null, 2));
                        if (onShowToast) {
                          onShowToast('Full agent JSON copied to clipboard!', 'success');
                        }
                      } catch (error) {
                        if (onShowToast) {
                          onShowToast('Failed to copy JSON', 'error');
                        }
                      }
                    }}
                    className="flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors duration-200"
                  >
                    <ClipboardDocumentIcon className="h-4 w-4" />
                    Copy JSON
                  </button>
                </div>

                {loadingDetails ? (
                  <div className="p-4 bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg text-center text-gray-600 dark:text-gray-400">
                    Loading full agent details...
                  </div>
                ) : (
                  <pre className="p-4 bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg overflow-x-auto text-xs text-gray-900 dark:text-gray-100 max-h-[30vh] overflow-y-auto">
                    {JSON.stringify(fullAgentDetails || agent, null, 2)}
                  </pre>
                )}
              </div>

              {/* Field Legend */}
              <div className="bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-white mb-3">
                  Field Reference
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <h5 className="font-medium text-gray-700 dark:text-gray-300 mb-2">Core Fields</h5>
                    <ul className="space-y-1 text-gray-600 dark:text-gray-400">
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">protocol_version</code> - A2A protocol version</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">name</code> - Agent display name</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">description</code> - Agent purpose</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">url</code> - Agent endpoint URL</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">path</code> - Registry path</li>
                    </ul>
                  </div>
                  <div>
                    <h5 className="font-medium text-gray-700 dark:text-gray-300 mb-2">Metadata Fields</h5>
                    <ul className="space-y-1 text-gray-600 dark:text-gray-400">
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">skills</code> - Agent capabilities</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">security_schemes</code> - Auth methods</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">tags</code> - Categorization</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">trust_level</code> - Verification status</li>
                      <li><code className="bg-gray-200 dark:bg-gray-700 px-1 rounded">metadata</code> - Custom data</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 max-w-3xl w-full mx-4 max-h-[80vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                A2A Agent Configuration for {agent.name}
              </h3>
              <button
                onClick={() => setShowConfig(false)}
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              {/* Instructions */}
              <div className="bg-cyan-50 dark:bg-cyan-900/20 border border-cyan-200 dark:border-cyan-800 rounded-lg p-4">
                <h4 className="font-medium text-cyan-900 dark:text-cyan-100 mb-2">
                  How to use this configuration:
                </h4>
                <ol className="text-sm text-cyan-800 dark:text-cyan-200 space-y-1 list-decimal list-inside">
                  <li>Copy the configuration below</li>
                  <li>Paste it into your agent configuration file</li>
                  <li>Replace <code className="bg-cyan-100 dark:bg-cyan-800 px-1 rounded">[YOUR_AUTH_TOKEN]</code> with your gateway authentication token</li>
                  <li>Restart your AI coding assistant to load the new agent</li>
                </ol>
              </div>

              {/* Authentication Note */}
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                <h4 className="font-medium text-amber-900 dark:text-amber-100 mb-2">
                  Authentication Required
                </h4>
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  This configuration requires gateway authentication tokens. The tokens authenticate your AI assistant
                  with the MCP Gateway, not the individual agent. Visit the authentication documentation for setup instructions.
                </p>
              </div>

              {/* CLI Commands Section */}
              <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
                <h4 className="font-medium text-purple-900 dark:text-purple-100 mb-3">
                  CLI Agent Management Commands
                </h4>
                <p className="text-sm text-purple-800 dark:text-purple-200 mb-4">
                  Manage agents from the command line using the A2A CLI. Reference the <a href="https://github.com/agentic-community/mcp-gateway-registry/blob/main/docs/a2a-agent-management.md" target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline">A2A Agent Management Guide</a> for complete documentation.
                </p>

                <div className="mb-3">
                  <label className="block text-sm font-medium text-purple-900 dark:text-purple-100 mb-2">
                    Select Command:
                  </label>
                  <select
                    value={selectedCliCommand}
                    onChange={(e) => setSelectedCliCommand(e.target.value as any)}
                    className="w-full px-3 py-2 border border-purple-300 dark:border-purple-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  >
                    <option value="list">List agents</option>
                    <option value="get">Get agent details</option>
                    <option value="test">Test agent (single)</option>
                    <option value="test-all">Test all agents</option>
                    <option value="search">Search agents</option>
                    <option value="register">Register agent</option>
                    <option value="update">Update agent</option>
                    <option value="toggle">Toggle agent (enable/disable)</option>
                    <option value="delete">Delete agent</option>
                  </select>
                </div>

                <div className="mb-3">
                  <p className="text-xs text-purple-700 dark:text-purple-300 mb-2">
                    <strong>Description:</strong> {getCliCommandDescription()}
                  </p>
                </div>

                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-xs font-medium text-purple-900 dark:text-purple-100">Command:</span>
                  <button
                    onClick={copyCliCommandToClipboard}
                    className="flex items-center gap-1 px-2 py-1 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded transition-colors duration-200"
                  >
                    <ClipboardDocumentIcon className="h-3.5 w-3.5" />
                    Copy
                  </button>
                </div>

                <pre className="p-3 bg-gray-900 text-green-400 border border-purple-300 dark:border-purple-600 rounded text-xs overflow-x-auto font-mono whitespace-pre-wrap break-words">
                  {generateCliCommand()}
                </pre>

                <p className="text-xs text-purple-700 dark:text-purple-300 mt-3">
                  <strong>Note:</strong> Generate fresh credentials before running: <code className="bg-purple-100 dark:bg-purple-900 px-1 rounded">./credentials-provider/generate_creds.sh</code>
                </p>
              </div>

              {/* IDE Selection */}
              <div className="bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-white mb-3">
                  Select your IDE/Tool:
                </h4>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setSelectedIDE('vscode')}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      selectedIDE === 'vscode'
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    VS Code
                  </button>
                  <button
                    onClick={() => setSelectedIDE('cursor')}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      selectedIDE === 'cursor'
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    Cursor
                  </button>
                  <button
                    onClick={() => setSelectedIDE('cline')}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      selectedIDE === 'cline'
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    Cline
                  </button>
                  <button
                    onClick={() => setSelectedIDE('claude-code')}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      selectedIDE === 'claude-code'
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    Claude Code
                  </button>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                  Configuration format optimized for {selectedIDE === 'vscode' ? 'VS Code' : selectedIDE === 'cursor' ? 'Cursor' : selectedIDE === 'cline' ? 'Cline' : 'Claude Code'} integration
                </p>
              </div>

              {/* Configuration JSON */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="font-medium text-gray-900 dark:text-white">
                    Configuration JSON:
                  </h4>
                  <button
                    onClick={copyConfigToClipboard}
                    className="flex items-center gap-2 px-3 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg transition-colors duration-200"
                  >
                    <ClipboardDocumentIcon className="h-4 w-4" />
                    Copy to Clipboard
                  </button>
                </div>

                <pre className="p-4 bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg overflow-x-auto text-sm text-gray-900 dark:text-gray-100">
                  {JSON.stringify(generateAgentConfig(), null, 2)}
                </pre>
              </div>

              {/* Agent Information */}
              <div className="bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 dark:text-white mb-2">
                  Agent Information
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 dark:text-gray-400">Version:</span>
                    <span className="text-gray-900 dark:text-white font-medium">{agent.version || 'N/A'}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 dark:text-gray-400">Trust Level:</span>
                    <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${getTrustLevelColor()}`}>
                      {agent.trust_level?.toUpperCase() || 'COMMUNITY'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 dark:text-gray-400">Visibility:</span>
                    <span className="text-gray-900 dark:text-white font-medium">{agent.visibility?.toUpperCase() || 'PRIVATE'}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AgentCard;

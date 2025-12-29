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
  ShieldCheckIcon,
  GlobeAltIcon,
  LockClosedIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';
import AgentDetailsModal from './AgentDetailsModal';
import StarRatingWidget from './StarRatingWidget';

/**
 * Agent interface representing an A2A agent.
 */
export interface Agent {
  name: string;
  path: string;
  url?: string;
  description?: string;
  version?: string;
  visibility?: 'public' | 'private' | 'group-restricted';
  trust_level?: 'community' | 'verified' | 'trusted' | 'unverified';
  enabled: boolean;
  tags?: string[];
  last_checked_time?: string;
  usersCount?: number;
  rating?: number;
  rating_details?: Array<{ user: string; rating: number }>;
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
  authToken?: string | null;
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

const normalizeHealthStatus = (status?: string | null): Agent['status'] => {
  if (status === 'healthy' || status === 'healthy-auth-expired') {
    return status;
  }
  if (status === 'unhealthy') {
    return 'unhealthy';
  }
  return 'unknown';
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
  onAgentUpdate,
  authToken
}) => {
  const [showDetails, setShowDetails] = useState(false);
  const [loadingRefresh, setLoadingRefresh] = useState(false);
  const [fullAgentDetails, setFullAgentDetails] = useState<any>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

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
      const headers = authToken ? { Authorization: `Bearer ${authToken}` } : undefined;
      const response = await axios.post(
        `/api/agents${agent.path}/health`,
        undefined,
        headers ? { headers } : undefined
      );

      // Update just this agent instead of triggering global refresh
      if (onAgentUpdate && response.data) {
        const updates: Partial<Agent> = {
          status: normalizeHealthStatus(response.data.status),
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
  }, [agent.path, authToken, loadingRefresh, onRefreshSuccess, onShowToast, onAgentUpdate]);

  const handleCopyDetails = useCallback(
    async (data: any) => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        onShowToast?.('Full agent JSON copied to clipboard!', 'success');
      } catch (error) {
        console.error('Failed to copy JSON:', error);
        onShowToast?.('Failed to copy JSON', 'error');
      }
    },
    [onShowToast]
  );

  return (
    <>
      <div className="group rounded-2xl shadow-sm hover:shadow-xl transition-all duration-300 h-full flex flex-col bg-gradient-to-br from-cyan-50 to-blue-50 dark:from-cyan-900/20 dark:to-blue-900/20 border-2 border-cyan-200 dark:border-cyan-700 hover:border-cyan-300 dark:hover-border-cyan-600">
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
                {/* Check if this is an ASOR agent */}
                {(agent.tags?.includes('asor') || (agent as any).provider === 'ASOR') && (
                  <span className="px-2 py-0.5 text-xs font-semibold bg-gradient-to-r from-orange-100 to-red-100 text-orange-700 dark:from-orange-900/30 dark:to-red-900/30 dark:text-orange-300 rounded-full flex-shrink-0 border border-orange-200 dark:border-orange-600">
                    ASOR
                  </span>
                )}
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
              {agent.url && (
                <a
                  href={agent.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-cyan-700 dark:text-cyan-300 break-all hover:underline"
                >
                  <span className="font-mono">{agent.url}</span>
                </a>
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
            <StarRatingWidget
              resourceType="agents"
              path={agent.path}
              initialRating={agent.rating || 0}
              initialCount={agent.rating_details?.length || 0}
              authToken={authToken}
              onShowToast={onShowToast}
              onRatingUpdate={(newRating) => {
                // Update local agent rating when user submits rating
                if (onAgentUpdate) {
                  onAgentUpdate(agent.path, { rating: newRating });
                }
              }}
            />
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
              <label className="relative inline-flex items-center cursor-pointer" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={agent.enabled}
                  onChange={(e) => {
                    e.stopPropagation();
                    onToggle(agent.path, e.target.checked);
                  }}
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

      <AgentDetailsModal
        agent={agent}
        isOpen={showDetails}
        onClose={() => setShowDetails(false)}
        loading={loadingDetails}
        fullDetails={fullAgentDetails}
        onCopy={handleCopyDetails}
      />

    </>
  );
};

export default AgentCard;

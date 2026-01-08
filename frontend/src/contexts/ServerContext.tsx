import axios from 'axios';
import type React from 'react';
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import SERVICES from '@/services';
import { SERVER_CONNECTION, type SERVER_STATUS } from '@/services/mcp/type';

interface Server {
  id: string;
  name: string;
  path: string;
  description?: string;
  official?: boolean;
  enabled: boolean;
  tags?: string[];
  last_checked_time?: string;
  usersCount?: number;
  rating?: number;
  status?: 'active' | 'inactive' | 'error';
  num_tools?: number;
  proxy_pass_url?: string;
  license?: string;
  num_stars?: number;
  is_python?: boolean;
}

interface Agent {
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
  status?: 'healthy' | 'healthy-auth-expired' | 'unhealthy' | 'unknown';
}

interface ServerStats {
  total: number;
  enabled: number;
  disabled: number;
  withIssues: number;
}

interface AgentStats {
  total: number;
  enabled: number;
  disabled: number;
  withIssues: number;
}

interface ServerContextType {
  // Server state
  servers: Server[];
  setServers: React.Dispatch<React.SetStateAction<Server[]>>;
  stats: ServerStats;
  serverStatus: { [serverName: string]: SERVER_STATUS };
  setServerStatus: React.Dispatch<React.SetStateAction<{ [serverName: string]: SERVER_STATUS }>>;

  // Agent state
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  agentStats: AgentStats;

  // Shared state
  viewMode: 'all' | 'servers' | 'agents';
  setViewMode: (mode: 'all' | 'servers' | 'agents') => void;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
  loading: boolean;
  error: string | null;

  // Actions
  refreshData: (notLoading?: boolean) => Promise<void>;
  toggleAgent: (path: string, enabled: boolean) => Promise<void>;
  refreshServerStatus: () => Promise<Record<string, SERVER_STATUS>>;
  getServerStatusByPolling: (serverNames: string) => void;
  cancelPolling: (serverName?: string) => void;
}

const ServerContext = createContext<ServerContextType | undefined>(undefined);

export const useServer = () => {
  const context = useContext(ServerContext);
  if (context === undefined) {
    throw new Error('useServer must be used within an ServerProvider');
  }
  return context;
};

interface ServerProviderProps {
  children: ReactNode;
}

export const ServerProvider: React.FC<ServerProviderProps> = ({ children }) => {
  const [servers, setServers] = useState<Server[]>([]);
  const [serverStatus, setServerStatus] = useState<Record<string, SERVER_STATUS>>({});
  const [agents, setAgents] = useState<Agent[]>([]);
  const [viewMode, setViewMode] = useState<'all' | 'servers' | 'agents'>('all');
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<Record<string, NodeJS.Timeout>>({});

  // Calculate server stats
  const stats = useMemo<ServerStats>(
    () => ({
      total: servers.length,
      enabled: servers.filter(s => s.enabled).length,
      disabled: servers.filter(s => !s.enabled).length,
      withIssues: servers.filter(s => s.status === 'inactive').length,
    }),
    [servers],
  );

  // Calculate agent stats
  const agentStats = useMemo<AgentStats>(
    () => ({
      total: agents.length,
      enabled: agents.filter(a => a.enabled).length,
      disabled: agents.filter(a => !a.enabled).length,
      withIssues: agents.filter(a => a.status === 'unhealthy').length,
    }),
    [agents],
  );

  useEffect(() => {
    refreshData();
    fetchServerStatus();
    return () => {
      // Clear all timeouts on unmount
      Object.values(timeoutRef.current).forEach(timeout => {
        clearTimeout(timeout);
      });
      timeoutRef.current = {};
    };
  }, []);

  // Helper function to map backend health status to frontend status
  const mapHealthStatus = (healthStatus: string): 'healthy' | 'unhealthy' | 'unknown' => {
    if (!healthStatus || healthStatus === 'unknown') return 'unknown';
    if (healthStatus === 'healthy') return 'healthy';
    if (healthStatus.includes('unhealthy') || healthStatus.includes('error') || healthStatus.includes('timeout'))
      return 'unhealthy';
    return 'unknown';
  };

  const refreshData = useCallback(async (notLoading?: boolean) => {
    try {
      if (!notLoading) setLoading(true);
      setError(null);

      // Fetch both servers and agents in parallel
      const [serversResponse, agentsResponse] = await Promise.all([
        SERVICES.SERVER.getServers(),
        axios
          .get('/api/agents')
          .catch(() => ({ data: { agents: [] } })), // Graceful fallback for agents
      ]);

      // Process servers
      const serversList = serversResponse.servers || [];

      console.log('🔍 Server filtering debug info:');
      console.log(`📊 Total servers returned from API: ${serversList.length}`);

      const transformedServers: Server[] = serversList.map((serverInfo: any) => {
        console.log(`🕐 Server ${serverInfo.display_name}: last_checked_iso =`, serverInfo.last_checked_iso);

        return {
          id: serverInfo.id,
          name: serverInfo.server_name || 'Unknown Server',
          path: serverInfo.path,
          description: serverInfo.description || '',
          official: serverInfo.is_official || false, // undefined
          enabled: serverInfo.is_enabled !== undefined ? serverInfo.is_enabled : false, // undefined
          tags: serverInfo.tags || [],
          last_checked_time: serverInfo.updatedAt,
          usersCount: 0,
          rating: serverInfo.num_stars || 0,
          status: serverInfo.status || 'unknown', // undefined
          num_tools: serverInfo.num_tools || 0,
          proxy_pass_url: serverInfo.proxy_pass_url,
          license: serverInfo.license,
          num_stars: serverInfo.num_stars || 0,
          is_python: serverInfo.is_python || false,
        };
      });

      // Process agents
      const agentsData = agentsResponse.data || {};
      const agentsList = agentsData.agents || [];

      console.log('🔍 Agent filtering debug info:');
      console.log(`📊 Total agents returned from API: ${agentsList.length}`);

      const transformedAgents: Agent[] = agentsList.map((agentInfo: any) => ({
        name: agentInfo.display_name || agentInfo.name || 'Unknown Agent',
        path: agentInfo.path,
        url: agentInfo.url,
        description: agentInfo.description || '',
        version: agentInfo.version,
        visibility: agentInfo.visibility || 'private',
        trust_level: agentInfo.trust_level || 'community',
        enabled: agentInfo.is_enabled !== undefined ? agentInfo.is_enabled : false,
        tags: agentInfo.tags || [],
        last_checked_time: agentInfo.last_checked_iso,
        usersCount: 0,
        rating: agentInfo.num_stars || 0,
        status: mapHealthStatus(agentInfo.health_status || 'unknown'),
      }));

      setServers(transformedServers);
      setAgents(transformedAgents);
    } catch (err: any) {
      console.error('Failed to fetch data:', err);
      setError(err?.detail || 'Failed to fetch data');
      setServers([]);
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Toggle agent
  const toggleAgent = useCallback(
    async (path: string, enabled: boolean) => {
      // Optimistic update
      setAgents(prev => prev.map(a => (a.path === path ? { ...a, enabled } : a)));

      try {
        await axios.post(`/api/agents${path}/toggle`, { enabled });
      } catch (err) {
        console.error('Error toggling agent:', err);
        // Revert on error
        await refreshData();
        throw err;
      }
    },
    [refreshData],
  );

  const fetchServerStatus = useCallback(async () => {
    try {
      const result = await SERVICES.MCP.getServerStatus();
      const serverStatusData = result?.connectionStatus || {};
      setServerStatus(serverStatusData);
      return serverStatusData;
    } catch (error: any) {
      console.error('Failed to fetch server status:', error.data?.detail || 'error');
      return {};
    } finally {
      // setLoading(false);
    }
  }, []);

  const getServerStatusByPolling = useCallback(
    async (serverName: string) => {
      // Clear existing timeout for this specific server if it exists
      if (timeoutRef.current[serverName]) {
        clearTimeout(timeoutRef.current[serverName]);
        delete timeoutRef.current[serverName];
      }

      console.log(`🔄 Polling server status for`, serverName);
      const initialState = serverStatus[serverName]?.connection_state;

      const poll = async () => {
        const latestStatusData = await fetchServerStatus();
        const currentState = latestStatusData[serverName]?.connection_state;

        if (currentState === initialState || currentState === SERVER_CONNECTION.CONNECTING) {
          timeoutRef.current[serverName] = setTimeout(() => {
            poll();
          }, 5000);
        } else {
          // Stop polling for this server
          if (timeoutRef.current[serverName]) {
            clearTimeout(timeoutRef.current[serverName]);
            delete timeoutRef.current[serverName];
          }
        }
      };

      await poll();
    },
    [serverStatus, fetchServerStatus],
  );

  const cancelPolling = useCallback((serverName?: string) => {
    if (serverName) {
      if (timeoutRef.current[serverName]) {
        clearTimeout(timeoutRef.current[serverName]);
        delete timeoutRef.current[serverName];
      }
    } else {
      Object.values(timeoutRef.current).forEach(timeout => {
        clearTimeout(timeout);
      });
      timeoutRef.current = {};
    }
  }, []);

  const value: ServerContextType = {
    servers,
    setServers,
    stats,
    serverStatus,
    setServerStatus,
    agents,
    setAgents,
    agentStats,
    viewMode,
    setViewMode,
    activeFilter,
    setActiveFilter,
    loading,
    error,
    refreshData,
    toggleAgent,
    refreshServerStatus: fetchServerStatus,
    getServerStatusByPolling,
    cancelPolling,
  };

  return <ServerContext.Provider value={value}>{children}</ServerContext.Provider>;
};

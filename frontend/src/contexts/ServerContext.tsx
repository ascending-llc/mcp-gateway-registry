import React, { createContext, useContext, useState, useEffect, ReactNode, useMemo, useCallback } from 'react';
import axios from 'axios';

interface Server {
  name: string;
  path: string;
  description?: string;
  official?: boolean;
  enabled: boolean;
  tags?: string[];
  last_checked_time?: string;
  usersCount?: number;
  rating?: number;
  status?: 'healthy' | 'healthy-auth-expired' | 'unhealthy' | 'unknown';
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
  refreshData: () => Promise<void>;
  toggleServer: (path: string, enabled: boolean) => Promise<void>;
  toggleAgent: (path: string, enabled: boolean) => Promise<void>;
}

const ServerContext = createContext<ServerContextType | undefined>(undefined);

export const useServer = () => {
  const context = useContext(ServerContext);
  if (context === undefined) {
    throw new Error('useServer must be used within an ServerProvider');
  }
  return context;
}

interface ServerProviderProps {
  children: ReactNode;
}

export const ServerProvider: React.FC<ServerProviderProps> = ({ children }) => {
    const [servers, setServers] = useState<Server[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [viewMode, setViewMode] = useState<'all' | 'servers' | 'agents'>('all');
    const [activeFilter, setActiveFilter] = useState<string>('all');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Calculate server stats
    const stats = useMemo<ServerStats>(() => ({
      total: servers.length,
      enabled: servers.filter(s => s.enabled).length,
      disabled: servers.filter(s => !s.enabled).length,
      withIssues: servers.filter(s => s.status === 'unhealthy').length,
    }), [servers]);

    // Calculate agent stats
    const agentStats = useMemo<AgentStats>(() => ({
      total: agents.length,
      enabled: agents.filter(a => a.enabled).length,
      disabled: agents.filter(a => !a.enabled).length,
      withIssues: agents.filter(a => a.status === 'unhealthy').length,
    }), [agents]);

    useEffect(() => {
      refreshData();
    }, []);

    // Helper function to map backend health status to frontend status
    const mapHealthStatus = (healthStatus: string): 'healthy' | 'unhealthy' | 'unknown' => {
        if (!healthStatus || healthStatus === 'unknown') return 'unknown';
        if (healthStatus === 'healthy') return 'healthy';
        if (healthStatus.includes('unhealthy') || healthStatus.includes('error') || healthStatus.includes('timeout')) return 'unhealthy';
        return 'unknown';
    };

    // Fetch both servers and agents
    const refreshData = useCallback(async () => {
        try {
          setLoading(true);
          setError(null);
          
          // Fetch both servers and agents in parallel
          const [serversResponse, agentsResponse] = await Promise.all([
            axios.get('/api/servers'),
            axios.get('/api/agents').catch(() => ({ data: { agents: [] } })) // Graceful fallback for agents
          ]);

          // Process servers
          const responseData = serversResponse.data || {};
          const serversList = responseData.servers || [];
          
          console.log('🔍 Server filtering debug info:');
          console.log(`📊 Total servers returned from API: ${serversList.length}`);
        
          const transformedServers: Server[] = serversList.map((serverInfo: any) => {
            console.log(`🕐 Server ${serverInfo.display_name}: last_checked_iso =`, serverInfo.last_checked_iso);
            
            return {
              name: serverInfo.display_name || 'Unknown Server',
              path: serverInfo.path,
              description: serverInfo.description || '',
              official: serverInfo.is_official || false,
              enabled: serverInfo.is_enabled !== undefined ? serverInfo.is_enabled : false,
              tags: serverInfo.tags || [],
              last_checked_time: serverInfo.last_checked_iso,
              usersCount: 0,
              rating: serverInfo.num_stars || 0,
              status: mapHealthStatus(serverInfo.health_status || 'unknown'),
              num_tools: serverInfo.num_tools || 0,
              proxy_pass_url: serverInfo.proxy_pass_url,
              license: serverInfo.license,
              num_stars: serverInfo.num_stars || 0,
              is_python: serverInfo.is_python || false
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
            status: mapHealthStatus(agentInfo.health_status || 'unknown')
          }));
          
          setServers(transformedServers);
          setAgents(transformedAgents);
        } catch (err: any) {
          console.error('Failed to fetch data:', err);
          setError(err.response?.data?.detail || 'Failed to fetch data');
          setServers([]);
          setAgents([]);
        } finally {
          setLoading(false);
        }
    }, []);
    // Toggle server
    const toggleServer = useCallback(async (path: string, enabled: boolean) => {
      // Optimistic update
      setServers(prev => 
        prev.map(s => s.path === path ? { ...s, enabled } : s)
      );

      try {
        const formData = new FormData();
        formData.append('enabled', enabled.toString());
        await axios.post(`/api/toggle${path}`, formData);
      } catch (err) {
        console.error('Error toggling server:', err);
        // Revert on error
        await refreshData();
        throw err;
      }
    }, [refreshData]);

    // Toggle agent
    const toggleAgent = useCallback(async (path: string, enabled: boolean) => {
      // Optimistic update
      setAgents(prev => 
        prev.map(a => a.path === path ? { ...a, enabled } : a)
      );

      try {
        await axios.post(`/api/agents${path}/toggle`, { enabled });
      } catch (err) {
        console.error('Error toggling agent:', err);
        // Revert on error
        await refreshData();
        throw err;
      }
    }, [refreshData]);

    const value: ServerContextType = {
      servers,
      setServers,
      stats,
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
      toggleServer,
      toggleAgent,
    };

    return <ServerContext.Provider value={value}>{children}</ServerContext.Provider>;

}
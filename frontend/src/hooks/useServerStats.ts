import React, { useState, useEffect, useCallback } from 'react';
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
  status?: 'healthy' | 'unhealthy' | 'unknown';
  num_tools?: number;
}

interface ServerStats {
  total: number;
  enabled: number;
  disabled: number;
  withIssues: number;
}

interface UseServerStatsReturn {
  stats: ServerStats;
  servers: Server[];
  setServers: React.Dispatch<React.SetStateAction<Server[]>>;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
  loading: boolean;
  error: string | null;
  refreshData: () => Promise<void>;
}

export const useServerStats = (): UseServerStatsReturn => {
  const [stats, setStats] = useState<ServerStats>({
    total: 0,
    enabled: 0,
    disabled: 0,
    withIssues: 0,
  });
  const [servers, setServers] = useState<Server[]>([]);
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Helper function to map backend health status to frontend status
  const mapHealthStatus = (healthStatus: string): 'healthy' | 'unhealthy' | 'unknown' => {
    if (!healthStatus || healthStatus === 'unknown') return 'unknown';
    if (healthStatus === 'healthy') return 'healthy';
    if (healthStatus.includes('unhealthy') || healthStatus.includes('error') || healthStatus.includes('timeout')) return 'unhealthy';
    return 'unknown';
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Call the servers API endpoint
      const response = await axios.get('/api/servers');
      
      // The API returns {"servers": [...]} 
      const responseData = response.data || {};
      const serversList = responseData.servers || [];
      
      // Debug logging to see what servers are returned
      console.log('🔍 Server filtering debug info:');
      console.log(`📊 Total servers returned from API: ${serversList.length}`);
      console.log('📋 Server list:', serversList.map((s: any) => ({ 
        name: s.display_name, 
        path: s.path, 
        enabled: s.is_enabled 
      })));
      
      // Transform server data from backend format to frontend format
      const transformedServers: Server[] = serversList.map((serverInfo: any) => {
        // Debug log to see what last_checked_iso data we're getting
        console.log(`🕐 Server ${serverInfo.display_name}: last_checked_iso =`, serverInfo.last_checked_iso);
        
        const transformed = {
          name: serverInfo.display_name || 'Unknown Server',
          path: serverInfo.path,
          description: serverInfo.description || '',
          official: serverInfo.is_official || false,
          enabled: serverInfo.is_enabled !== undefined ? serverInfo.is_enabled : false,
          tags: serverInfo.tags || [],
          last_checked_time: serverInfo.last_checked_iso,  // Fixed field mapping
          usersCount: 0, // Not available in backend
          rating: serverInfo.num_stars || 0,
          status: mapHealthStatus(serverInfo.health_status || 'unknown'),
          num_tools: serverInfo.num_tools || 0
        };
        
        // Debug log the transformed server
        console.log(`🔄 Transformed server ${transformed.name}:`, {
          last_checked_time: transformed.last_checked_time,
          status: transformed.status,
          enabled: transformed.enabled
        });
        
        return transformed;
      });
      
      setServers(transformedServers);
      
      // Calculate stats
      let total = 0;
      let enabled = 0;
      let disabled = 0;
      let withIssues = 0;
      
      transformedServers.forEach((server) => {
        total++;
        if (server.enabled) {
          enabled++;
        } else {
          disabled++;
        }
        
        // Check if server has issues (unhealthy status)
        if (server.status === 'unhealthy') {
          withIssues++;
        }
      });
      
      const newStats = {
        total,
        enabled,
        disabled,
        withIssues,
      };
      
      console.log('📈 Calculated stats:', newStats);
      setStats(newStats);
    } catch (err: any) {
      console.error('Failed to fetch server data:', err);
      setError(err.response?.data?.detail || 'Failed to fetch server data');
      setServers([]);
      setStats({ total: 0, enabled: 0, disabled: 0, withIssues: 0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    stats,
    servers,
    setServers,
    activeFilter,
    setActiveFilter,
    loading,
    error,
    refreshData: fetchData,
  };
}; 
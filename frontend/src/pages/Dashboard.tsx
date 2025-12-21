import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { MagnifyingGlassIcon, PlusIcon, XMarkIcon, ArrowPathIcon, CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline';
import { useServerStats } from '../hooks/useServerStats';
import { useAuth } from '../contexts/AuthContext';
import ServerCard from '../components/ServerCard';
import AgentCard from '../components/AgentCard';
import SemanticSearchResults from '../components/SemanticSearchResults';
import { useSemanticSearch } from '../hooks/useSemanticSearch';
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

// Toast notification component
interface ToastProps {
  message: string;
  type: 'success' | 'error';
  onClose: () => void;
}

const Toast: React.FC<ToastProps> = ({ message, type, onClose }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, 4000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className="fixed top-4 right-4 z-50 animate-slide-in-top">
      <div className={`flex items-center p-4 rounded-lg shadow-lg border ${
        type === 'success'
          ? 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/50 dark:border-green-700 dark:text-green-200'
          : 'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/50 dark:border-red-700 dark:text-red-200'
      }`}>
        {type === 'success' ? (
          <CheckCircleIcon className="h-5 w-5 mr-3 flex-shrink-0" />
        ) : (
          <ExclamationCircleIcon className="h-5 w-5 mr-3 flex-shrink-0" />
        )}
        <p className="text-sm font-medium">{message}</p>
        <button
          onClick={onClose}
          className="ml-3 flex-shrink-0 text-current opacity-70 hover:opacity-100"
        >
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

const normalizeAgentStatus = (status?: string | null): Agent['status'] => {
  if (status === 'healthy' || status === 'healthy-auth-expired') {
    return status;
  }
  if (status === 'unhealthy') {
    return 'unhealthy';
  }
  return 'unknown';
};

const buildAgentAuthHeaders = (token?: string | null) =>
  token ? { Authorization: `Bearer ${token}` } : undefined;

interface DashboardProps {
  activeFilter?: string;
}

const Dashboard: React.FC<DashboardProps> = ({ activeFilter = 'all' }) => {
  const { servers, loading, error, refreshData, setServers } = useServerStats();
  const { user } = useAuth();
  const [searchTerm, setSearchTerm] = useState('');
  const [committedQuery, setCommittedQuery] = useState('');
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [registerForm, setRegisterForm] = useState({
    name: '',
    path: '',
    proxyPass: '',
    description: '',
    official: false,
    tags: [] as string[]
  });
  const [registerLoading, setRegisterLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [editingServer, setEditingServer] = useState<Server | null>(null);
  const [editForm, setEditForm] = useState({
    name: '',
    path: '',
    proxyPass: '',
    description: '',
    tags: [] as string[],
    license: 'N/A',
    num_tools: 0,
    num_stars: 0,
    is_python: false
  });
  const [editLoading, setEditLoading] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // Agent state management
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [agentApiToken, setAgentApiToken] = useState<string | null>(null);

  // View filter state
  const [viewFilter, setViewFilter] = useState<'all' | 'servers' | 'agents' | 'external'>('all');
  const [editAgentForm, setEditAgentForm] = useState({
    name: '',
    path: '',
    description: '',
    version: '',
    visibility: 'private' as 'public' | 'private' | 'group-restricted',
    trust_level: 'community' as 'community' | 'verified' | 'trusted' | 'unverified',
    tags: [] as string[]
  });
  const [editAgentLoading, setEditAgentLoading] = useState(false);

  const handleAgentUpdate = useCallback((path: string, updates: Partial<Agent>) => {
    setAgents(prevAgents =>
      prevAgents.map(agent =>
        agent.path === path
          ? { ...agent, ...updates }
          : agent
      )
    );
  }, []);

  const performAgentHealthCheck = useCallback(async (agent: Agent, token?: string | null) => {
    if (!agent?.path) return;

    const headers = buildAgentAuthHeaders(token);
    try {
      const response = await axios.post(
        `/api/agents${agent.path}/health`,
        undefined,
        headers ? { headers } : undefined
      );

      handleAgentUpdate(agent.path, {
        status: normalizeAgentStatus(response.data?.status),
        last_checked_time: response.data?.last_checked_iso || null
      });
    } catch (error) {
      console.error(`Failed to check health for agent ${agent.name}:`, error);
      handleAgentUpdate(agent.path, {
        status: 'unhealthy',
        last_checked_time: new Date().toISOString()
      });
    }
  }, [handleAgentUpdate]);

  const runInitialAgentHealthChecks = useCallback((agentsList: Agent[], token?: string | null) => {
    const candidates = agentsList.filter(agent => agent.enabled);
    if (!candidates.length) return;

    Promise.allSettled(candidates.map(agent => performAgentHealthCheck(agent, token))).catch((error) => {
      console.error('Failed to run agent health checks:', error);
    });
  }, [performAgentHealthCheck]);

  // Fetch agents from the API
  const fetchAgents = useCallback(async () => {
    try {
      setAgentsLoading(true);
      setAgentsError(null);

      // First, get JWT token
      const tokenResponse = await axios.post('/api/tokens/generate', {
        description: 'Dashboard agent fetch',
        expires_in_hours: 1
      }, {
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!tokenResponse.data.success) {
        throw new Error('Failed to generate JWT token');
      }

      const jwtToken = tokenResponse.data.token_data.access_token;
      setAgentApiToken(jwtToken);

      // Fetch agents with JWT token
      const response = await axios.get('/api/agents', {
        headers: {
          'Authorization': `Bearer ${jwtToken}`
        }
      });

      const responseData = response.data || {};
      const agentsList = responseData.agents || [];

      console.log('Agent filtering debug info:');
      console.log(`Total agents returned from API: ${agentsList.length}`);
      console.log('Agent list:', agentsList.map((a: any) => ({
        name: a.name,
        path: a.path,
        enabled: a.enabled
      })));

      // Transform agent data from API format to frontend format
      const transformedAgents: Agent[] = agentsList.map((agentInfo: any) => {
        console.log(`Processing agent ${agentInfo.name}:`, agentInfo);

        const transformed = {
          name: agentInfo.name || 'Unknown Agent',
          path: agentInfo.path || '',
          url: agentInfo.url || '',
          description: agentInfo.description || '',
          trust_level: agentInfo.trust_level || 'community',
          enabled: agentInfo.is_enabled !== undefined ? agentInfo.is_enabled : false,
          tags: agentInfo.tags || [],
          rating: agentInfo.num_stars || 0,
          status: normalizeAgentStatus(agentInfo.status),
          last_checked_time: agentInfo.last_checked_time || null
        };

        console.log(`Transformed agent ${transformed.name}:`, {
          enabled: transformed.enabled,
          trust_level: transformed.trust_level,
          rating: transformed.rating
        });

        return transformed;
      });

      setAgents(transformedAgents);
      runInitialAgentHealthChecks(transformedAgents, jwtToken);
    } catch (err: any) {
      console.error('Failed to fetch agents:', err);
      setAgentsError(err.response?.data?.detail || 'Failed to fetch agents');
      setAgents([]);
      setAgentApiToken(null);
    } finally {
      setAgentsLoading(false);
    }
  }, [runInitialAgentHealthChecks]);

  // Fetch agents on component mount or when user changes
  useEffect(() => {
    if (user) {
      fetchAgents();
    }
  }, [user, fetchAgents]);

  // External registry tags - can be configured via environment or constants
  // Default tags that identify servers from external registries
  const EXTERNAL_REGISTRY_TAGS = ['anthropic-registry', 'workday-asor', 'asor', 'federated'];

  // Separate internal and external registry servers
  const internalServers = useMemo(() => {
    return servers.filter(s => {
      const serverTags = s.tags || [];
      return !EXTERNAL_REGISTRY_TAGS.some(tag => serverTags.includes(tag));
    });
  }, [servers]);

  const externalServers = useMemo(() => {
    return servers.filter(s => {
      const serverTags = s.tags || [];
      return EXTERNAL_REGISTRY_TAGS.some(tag => serverTags.includes(tag));
    });
  }, [servers]);

  // Separate internal and external registry agents
  const internalAgents = useMemo(() => {
    return agents.filter(a => {
      const agentTags = a.tags || [];
      return !EXTERNAL_REGISTRY_TAGS.some(tag => agentTags.includes(tag));
    });
  }, [agents]);

  const externalAgents = useMemo(() => {
    return agents.filter(a => {
      const agentTags = a.tags || [];
      return EXTERNAL_REGISTRY_TAGS.some(tag => agentTags.includes(tag));
    });
  }, [agents]);

  // Semantic search
  const semanticEnabled = committedQuery.trim().length >= 2;
  const {
    results: semanticResults,
    loading: semanticLoading,
    error: semanticError
  } = useSemanticSearch(committedQuery, {
    minLength: 2,
    maxResults: 12,
    enabled: semanticEnabled
  });

  const semanticServers = semanticResults?.servers ?? [];
  const semanticTools = semanticResults?.tools ?? [];
  const semanticAgents = semanticResults?.agents ?? [];
  const semanticDisplayQuery = semanticResults?.query || committedQuery || searchTerm;
  const semanticSectionVisible = semanticEnabled;
  const shouldShowFallbackGrid =
    semanticSectionVisible &&
    (Boolean(semanticError) ||
      (!semanticLoading &&
        semanticServers.length === 0 &&
        semanticTools.length === 0 &&
        semanticAgents.length === 0));

  // Filter servers based on activeFilter and searchTerm
  const filteredServers = useMemo(() => {
    let filtered = internalServers;

    // Apply filter first
    if (activeFilter === 'enabled') filtered = filtered.filter(s => s.enabled);
    else if (activeFilter === 'disabled') filtered = filtered.filter(s => !s.enabled);
    else if (activeFilter === 'unhealthy') filtered = filtered.filter(s => s.status === 'unhealthy');

    // Then apply search
    if (searchTerm) {
      const query = searchTerm.toLowerCase();
      filtered = filtered.filter(server =>
        server.name.toLowerCase().includes(query) ||
        (server.description || '').toLowerCase().includes(query) ||
        server.path.toLowerCase().includes(query) ||
        (server.tags || []).some(tag => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  }, [internalServers, activeFilter, searchTerm]);

  // Filter external servers based on searchTerm
  const filteredExternalServers = useMemo(() => {
    let filtered = externalServers;

    if (searchTerm) {
      const query = searchTerm.toLowerCase();
      filtered = filtered.filter(server =>
        server.name.toLowerCase().includes(query) ||
        (server.description || '').toLowerCase().includes(query) ||
        server.path.toLowerCase().includes(query) ||
        (server.tags || []).some(tag => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  }, [externalServers, searchTerm]);

  // Filter external agents based on searchTerm
  const filteredExternalAgents = useMemo(() => {
    let filtered = externalAgents;

    if (searchTerm) {
      const query = searchTerm.toLowerCase();
      filtered = filtered.filter(agent =>
        agent.name.toLowerCase().includes(query) ||
        (agent.description || '').toLowerCase().includes(query) ||
        agent.path.toLowerCase().includes(query) ||
        (agent.tags || []).some(tag => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  }, [externalAgents, searchTerm]);

  // Filter agents based on activeFilter and searchTerm
  const filteredAgents = useMemo(() => {
    let filtered = internalAgents;

    // Apply filter first
    if (activeFilter === 'enabled') filtered = filtered.filter(a => a.enabled);
    else if (activeFilter === 'disabled') filtered = filtered.filter(a => !a.enabled);
    else if (activeFilter === 'unhealthy') filtered = filtered.filter(a => a.status === 'unhealthy');

    // Then apply search
    if (searchTerm) {
      const query = searchTerm.toLowerCase();
      filtered = filtered.filter(agent =>
        agent.name.toLowerCase().includes(query) ||
        (agent.description || '').toLowerCase().includes(query) ||
        agent.path.toLowerCase().includes(query) ||
        (agent.tags || []).some(tag => tag.toLowerCase().includes(query))
      );
    }

    return filtered;
  }, [internalAgents, activeFilter, searchTerm]);

  // Debug logging for filtering
  console.log('Dashboard filtering debug:');
  console.log(`Current user:`, user);
  console.log(`Total servers from hook: ${servers.length}`);
  console.log(`Total agents from API: ${agents.length}`);
  console.log(`Active filter: ${activeFilter}`);
  console.log(`Search term: "${searchTerm}"`);
  console.log(`Filtered servers: ${filteredServers.length}`);
  console.log(`Filtered agents: ${filteredAgents.length}`);

  useEffect(() => {
    if (searchTerm.trim().length === 0 && committedQuery.length > 0) {
      setCommittedQuery('');
    }
  }, [searchTerm, committedQuery]);

  const handleSemanticSearch = useCallback(() => {
    const trimmed = searchTerm.trim();
    setCommittedQuery(trimmed);
  }, [searchTerm]);

  const handleClearSearch = useCallback(() => {
    setSearchTerm('');
    setCommittedQuery('');
  }, []);

  const handleChangeViewFilter = useCallback(
    (filter: typeof viewFilter) => {
      setViewFilter(filter);
      if (semanticSectionVisible) {
        setSearchTerm('');
        setCommittedQuery('');
      }
    },
    [semanticSectionVisible]
  );

  const handleRefreshHealth = async () => {
    setRefreshing(true);
    try {
      await refreshData();
      await fetchAgents();
    } finally {
      setRefreshing(false);
    }
  };

  const handleEditServer = async (server: Server) => {
    try {
      // Fetch full server details including proxy_pass_url and tags
      const response = await axios.get(`/api/server_details${server.path}`);
      const serverDetails = response.data;

      setEditingServer(server);
      setEditForm({
        name: serverDetails.server_name || server.name,
        path: server.path,
        proxyPass: serverDetails.proxy_pass_url || '',
        description: serverDetails.description || '',
        tags: serverDetails.tags || [],
        license: serverDetails.license || 'N/A',
        num_tools: serverDetails.num_tools || 0,
        num_stars: serverDetails.num_stars || 0,
        is_python: serverDetails.is_python || false
      });
    } catch (error) {
      console.error('Failed to fetch server details:', error);
      // Fallback to basic server data
      setEditingServer(server);
      setEditForm({
        name: server.name,
        path: server.path,
        proxyPass: '',
        description: server.description || '',
        tags: server.tags || [],
        license: 'N/A',
        num_tools: server.num_tools || 0,
        num_stars: 0,
        is_python: false
      });
    }
  };

  const handleEditAgent = async (agent: Agent) => {
    // For now, just populate the form with existing data
    // In the future, we might fetch additional details from an API
    setEditingAgent(agent);
    setEditAgentForm({
      name: agent.name,
      path: agent.path,
      description: agent.description || '',
      version: agent.version || '1.0.0',
      visibility: agent.visibility || 'private',
      trust_level: agent.trust_level || 'community',
      tags: agent.tags || []
    });
  };

  const handleCloseEdit = () => {
    setEditingServer(null);
    setEditingAgent(null);
  };

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type });
  };

  const hideToast = () => {
    setToast(null);
  };

  const handleSaveEdit = async () => {
    if (editLoading || !editingServer) return;

    try {
      setEditLoading(true);

      const formData = new FormData();
      formData.append('name', editForm.name);
      formData.append('description', editForm.description);
      formData.append('proxy_pass_url', editForm.proxyPass);
      formData.append('tags', editForm.tags.join(','));
      formData.append('license', editForm.license);
      formData.append('num_tools', editForm.num_tools.toString());
      formData.append('num_stars', editForm.num_stars.toString());
      formData.append('is_python', editForm.is_python.toString());

      // Use the correct edit endpoint with the server path
      await axios.post(`/api/edit${editingServer.path}`, formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      // Refresh server list
      await refreshData();
      setEditingServer(null);

      showToast('Server updated successfully!', 'success');
    } catch (error: any) {
      console.error('Failed to update server:', error);
      showToast(error.response?.data?.detail || 'Failed to update server', 'error');
    } finally {
      setEditLoading(false);
    }
  };

  const handleSaveEditAgent = async () => {
    if (editAgentLoading || !editingAgent) return;

    try {
      setEditAgentLoading(true);

      // TODO: Implement agent edit endpoint when backend is ready
      // For now, just show a message
      showToast('Agent editing is not yet implemented', 'error');

      // When backend is ready, uncomment and implement:
      // const formData = new FormData();
      // formData.append('name', editAgentForm.name);
      // formData.append('description', editAgentForm.description);
      // formData.append('version', editAgentForm.version);
      // formData.append('visibility', editAgentForm.visibility);
      // formData.append('trust_level', editAgentForm.trust_level);
      // formData.append('tags', editAgentForm.tags.join(','));
      //
      // await axios.post(`/api/agents${editingAgent.path}/edit`, formData, {
      //   headers: {
      //     'Content-Type': 'application/x-www-form-urlencoded',
      //   },
      // });
      //
      // await fetchAgents();
      // setEditingAgent(null);
      // showToast('Agent updated successfully!', 'success');
    } catch (error: any) {
      console.error('Failed to update agent:', error);
      showToast(error.response?.data?.detail || 'Failed to update agent', 'error');
    } finally {
      setEditAgentLoading(false);
    }
  };

  const handleToggleServer = async (path: string, enabled: boolean) => {
    // Optimistically update the UI first
    setServers(prevServers =>
      prevServers.map(server =>
        server.path === path
          ? { ...server, enabled }
          : server
      )
    );

    try {
      const formData = new FormData();
      formData.append('enabled', enabled ? 'on' : 'off');

      await axios.post(`/api/toggle${path}`, formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      // No need to refresh all data - the optimistic update is enough
      showToast(`Server ${enabled ? 'enabled' : 'disabled'} successfully!`, 'success');
    } catch (error: any) {
      console.error('Failed to toggle server:', error);

      // Revert the optimistic update on error
      setServers(prevServers =>
        prevServers.map(server =>
          server.path === path
            ? { ...server, enabled: !enabled }
            : server
        )
      );

      showToast(error.response?.data?.detail || 'Failed to toggle server', 'error');
    }
  };

  const handleToggleAgent = async (path: string, enabled: boolean) => {
    // Optimistically update the UI first
    setAgents(prevAgents =>
      prevAgents.map(agent =>
        agent.path === path
          ? { ...agent, enabled }
          : agent
      )
    );

    try {
      await axios.post(`/api/agents${path}/toggle?enabled=${enabled}`);

      showToast(`Agent ${enabled ? 'enabled' : 'disabled'} successfully!`, 'success');
    } catch (error: any) {
      console.error('Failed to toggle agent:', error);

      // Revert the optimistic update on error
      setAgents(prevAgents =>
        prevAgents.map(agent =>
          agent.path === path
            ? { ...agent, enabled: !enabled }
            : agent
        )
      );

      showToast(error.response?.data?.detail || 'Failed to toggle agent', 'error');
    }
  };

  const handleServerUpdate = (path: string, updates: Partial<Server>) => {
    setServers(prevServers =>
      prevServers.map(server =>
        server.path === path
          ? { ...server, ...updates }
          : server
      )
    );
  };

  const handleRegisterServer = useCallback(() => {
    setShowRegisterModal(true);
  }, []);

  const handleRegisterSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (registerLoading) return; // Prevent double submission

    try {
      setRegisterLoading(true);

      const formData = new FormData();
      formData.append('name', registerForm.name);
      formData.append('description', registerForm.description);
      formData.append('path', registerForm.path);
      formData.append('proxy_pass_url', registerForm.proxyPass);
      formData.append('tags', registerForm.tags.join(','));
      formData.append('license', 'MIT');

      await axios.post('/api/register', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      // Reset form and close modal
      setRegisterForm({
        name: '',
        path: '',
        proxyPass: '',
        description: '',
        official: false,
        tags: []
      });
      setShowRegisterModal(false);

      // Refresh server list
      await refreshData();

      showToast('Server registered successfully!', 'success');
    } catch (error: any) {
      console.error('Failed to register server:', error);
      showToast(error.response?.data?.detail || 'Failed to register server', 'error');
    } finally {
      setRegisterLoading(false);
    }
  }, [registerForm, registerLoading, refreshData]);

  const renderServerGrid = (
    list: Server[],
    options?: { emptyTitle?: string; emptySubtitle?: string; showRegisterCta?: boolean }
  ) => {
    if (list.length === 0) {
      const title = options?.emptyTitle ?? 'No servers found';
      const subtitle =
        options?.emptySubtitle ??
        (searchTerm || activeFilter !== 'all'
          ? 'Press Enter in the search bar to search semantically'
          : 'No servers are registered yet');
      const shouldShowCta =
        options?.showRegisterCta ?? (!searchTerm && activeFilter === 'all');

      return (
        <div className="text-center py-16">
          <div className="text-gray-400 text-xl mb-4">{title}</div>
          <p className="text-gray-500 dark:text-gray-300 text-base max-w-md mx-auto">{subtitle}</p>
          {shouldShowCta && (
            <button
              onClick={handleRegisterServer}
              className="mt-6 inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            >
              <PlusIcon className="h-5 w-5 mr-2" />
              Register Server
            </button>
          )}
        </div>
      );
    }

    return (
      <div
        className="grid pb-12"
        style={{
          gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
          gap: 'clamp(1.5rem, 3vw, 2.5rem)'
        }}
      >
        {list.map((server) => (
          <ServerCard
            key={server.path}
            server={server}
            onToggle={handleToggleServer}
            onEdit={handleEditServer}
            canModify={user?.can_modify_servers || false}
            onRefreshSuccess={refreshData}
            onShowToast={showToast}
            onServerUpdate={handleServerUpdate}
            authToken={agentApiToken}
          />
        ))}
      </div>
    );
  };

  const renderDashboardCollections = () => (
    <>
      {/* MCP Servers Section */}
      {(viewFilter === 'all' || viewFilter === 'servers') &&
        (filteredServers.length > 0 || (!searchTerm && activeFilter === 'all')) && (
          <div className="mb-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              MCP Servers
            </h2>

            {filteredServers.length === 0 ? (
              <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div className="text-gray-400 text-lg mb-2">No servers found</div>
                <p className="text-gray-500 dark:text-gray-300 text-sm">
                  {searchTerm || activeFilter !== 'all'
                    ? 'Press Enter in the search bar to search semantically'
                    : 'No servers are registered yet'}
                </p>
                {!searchTerm && activeFilter === 'all' && (
                  <button
                    onClick={handleRegisterServer}
                    className="mt-4 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 transition-colors"
                  >
                    <PlusIcon className="h-4 w-4 mr-2" />
                    Register Server
                  </button>
                )}
              </div>
            ) : (
              <div
                className="grid"
                style={{
                  gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                  gap: 'clamp(1.5rem, 3vw, 2.5rem)'
                }}
              >
                {filteredServers.map((server) => (
                  <ServerCard
                    key={server.path}
                    server={server}
                    onToggle={handleToggleServer}
                    onEdit={handleEditServer}
                    canModify={user?.can_modify_servers || false}
                    onRefreshSuccess={refreshData}
                    onShowToast={showToast}
                    onServerUpdate={handleServerUpdate}
                    authToken={agentApiToken}
                  />
                ))}
              </div>
            )}
          </div>
        )}

      {/* A2A Agents Section */}
      {(viewFilter === 'all' || viewFilter === 'agents') &&
        (filteredAgents.length > 0 || (!searchTerm && activeFilter === 'all')) && (
          <div className="mb-8">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              A2A Agents
            </h2>

            {agentsError ? (
              <div className="text-center py-12 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                <div className="text-red-500 text-lg mb-2">Failed to load agents</div>
                <p className="text-red-600 dark:text-red-400 text-sm">{agentsError}</p>
              </div>
            ) : agentsLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600"></div>
              </div>
            ) : filteredAgents.length === 0 ? (
              <div className="text-center py-12 bg-cyan-50 dark:bg-cyan-900/20 rounded-lg border border-cyan-200 dark:border-cyan-800">
                <div className="text-gray-400 text-lg mb-2">No agents found</div>
                <p className="text-gray-500 dark:text-gray-300 text-sm">
                  {searchTerm || activeFilter !== 'all'
                    ? 'Press Enter in the search bar to search semantically'
                    : 'No agents are registered yet'}
                </p>
              </div>
            ) : (
              <div
                className="grid"
                style={{
                  gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                  gap: 'clamp(1.5rem, 3vw, 2.5rem)'
                }}
              >
                {filteredAgents.map((agent) => (
                  <AgentCard
                    key={agent.path}
                    agent={agent}
                    onToggle={handleToggleAgent}
                    onEdit={handleEditAgent}
                    canModify={user?.can_modify_servers || false}
                    onRefreshSuccess={fetchAgents}
                    onShowToast={showToast}
                    onAgentUpdate={handleAgentUpdate}
                    authToken={agentApiToken}
                  />
                ))}
              </div>
            )}
          </div>
        )}

      {/* External Registries Section */}
      {viewFilter === 'external' && (
        <div className="mb-8">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
            External Registries
          </h2>

          {filteredExternalServers.length === 0 && filteredExternalAgents.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg border border-dashed border-gray-300 dark:border-gray-600">
              <div className="text-gray-400 text-lg mb-2">
                {externalServers.length === 0 && externalAgents.length === 0 ? 'No External Registries Available' : 'No Results Found'}
              </div>
              <p className="text-gray-500 dark:text-gray-300 text-sm max-w-md mx-auto">
                {externalServers.length === 0 && externalAgents.length === 0
                  ? 'External registry integrations (Anthropic, ASOR, and more) will be available soon'
                  : 'Press Enter in the search bar to search semantically'}
              </p>
            </div>
          ) : (
            <div>
              {/* External Servers */}
              {filteredExternalServers.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
                    Servers
                  </h3>
                  <div
                    className="grid"
                    style={{
                      gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                      gap: 'clamp(1.5rem, 3vw, 2.5rem)'
                    }}
                  >
                    {filteredExternalServers.map((server) => (
                      <ServerCard
                        key={server.path}
                        server={server}
                        onToggle={handleToggleServer}
                        onEdit={handleEditServer}
                        canModify={user?.can_modify_servers || false}
                        onRefreshSuccess={refreshData}
                        onShowToast={showToast}
                        onServerUpdate={handleServerUpdate}
                        authToken={agentApiToken}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* External Agents */}
              {filteredExternalAgents.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
                    Agents
                  </h3>
                  <div
                    className="grid"
                    style={{
                      gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                      gap: 'clamp(1.5rem, 3vw, 2.5rem)'
                    }}
                  >
                    {filteredExternalAgents.map((agent) => (
                      <AgentCard
                        key={agent.path}
                        agent={agent}
                        onToggle={handleToggleAgent}
                        onEdit={handleEditAgent}
                        canModify={user?.can_modify_servers || false}
                        onRefreshSuccess={fetchAgents}
                        onShowToast={showToast}
                        onAgentUpdate={handleAgentUpdate}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Empty state when both are filtered out */}
      {((viewFilter === 'all' && filteredServers.length === 0 && filteredAgents.length === 0) ||
        (viewFilter === 'servers' && filteredServers.length === 0) ||
        (viewFilter === 'agents' && filteredAgents.length === 0)) &&
        (searchTerm || activeFilter !== 'all') && (
          <div className="text-center py-16">
            <div className="text-gray-400 text-xl mb-4">No items found</div>
            <p className="text-gray-500 dark:text-gray-300 text-base max-w-md mx-auto">
              Press Enter in the search bar to search semantically
            </p>
          </div>
        )}
    </>
  );

  // Show error state
  if (error && agentsError) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <div className="text-red-500 text-lg">Failed to load servers and agents</div>
        <p className="text-gray-500 text-center">{error}</p>
        <p className="text-gray-500 text-center">{agentsError}</p>
        <button
          onClick={handleRefreshHealth}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
        >
          Try Again
        </button>
      </div>
    );
  }

  // Show loading state
  if (loading && agentsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  return (
    <>
      {/* Toast Notification */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={hideToast}
        />
      )}

      <div className="flex flex-col h-full">
        {/* Fixed Header Section */}
        <div className="flex-shrink-0 space-y-4 pb-4">
          {/* View Filter Tabs */}
          <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
            <button
              onClick={() => handleChangeViewFilter('all')}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                viewFilter === 'all'
                  ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              All
            </button>
            <button
              onClick={() => handleChangeViewFilter('servers')}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                viewFilter === 'servers'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              MCP Servers Only
            </button>
            <button
              onClick={() => handleChangeViewFilter('agents')}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                viewFilter === 'agents'
                  ? 'border-cyan-500 text-cyan-600 dark:text-cyan-400'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              A2A Agents Only
            </button>
            <button
              onClick={() => handleChangeViewFilter('external')}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                viewFilter === 'external'
                  ? 'border-green-500 text-green-600 dark:text-green-400'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              External Registries
            </button>
          </div>

          {/* Search Bar and Refresh Button */}
          <div className="flex gap-4 items-center">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
              </div>
              <input
                type="text"
                placeholder="Search servers, agents, descriptions, or tags… (Press Enter to run semantic search; typing filters locally.)"
                className="input pl-10 w-full"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSemanticSearch();
                  }
                }}
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  <XMarkIcon className="h-4 w-4" />
                </button>
              )}
            </div>

            <button
              onClick={handleRegisterServer}
              className="btn-primary flex items-center space-x-2 flex-shrink-0"
            >
              <PlusIcon className="h-4 w-4" />
              <span>Register Server</span>
            </button>

            <button
              onClick={handleRefreshHealth}
              disabled={refreshing}
              className="btn-secondary flex items-center space-x-2 flex-shrink-0"
            >
              <ArrowPathIcon className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span>Refresh Health</span>
            </button>
          </div>

          {/* Results count */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 dark:text-gray-300">
              {semanticSectionVisible ? (
                <>
                  Showing {semanticServers.length} servers and {semanticAgents.length} agents
                </>
              ) : (
                <>
                  Showing {filteredServers.length} servers and {filteredAgents.length} agents
                </>
              )}
              {activeFilter !== 'all' && (
                <span className="ml-2 px-2 py-1 text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300 rounded-full">
                  {activeFilter} filter active
                </span>
              )}
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Press Enter to run semantic search; typing filters locally.
            </p>
          </div>
        </div>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto min-h-0 space-y-10">
          {semanticSectionVisible ? (
            <>
              <SemanticSearchResults
                query={semanticDisplayQuery}
                loading={semanticLoading}
                error={semanticError}
                servers={semanticServers}
                tools={semanticTools}
                agents={semanticAgents}
              />

              {shouldShowFallbackGrid && (
                <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="text-base font-semibold text-gray-900 dark:text-gray-200">
                      Keyword search fallback
                    </h4>
                    {semanticError && (
                      <span className="text-xs font-medium text-red-500">
                        Showing local matches because semantic search is unavailable
                      </span>
                    )}
                  </div>
                  {renderDashboardCollections()}
                </div>
              )}
            </>
          ) : (
            renderDashboardCollections()
          )}
        </div>

        {/* Padding at bottom for scroll */}
        <div className="pb-12"></div>
      </div>

      {/* Register Server Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-md w-full max-h-[90vh] overflow-y-auto">
            <form onSubmit={handleRegisterSubmit} className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Register New Server
                </h3>
                <button
                  type="button"
                  onClick={() => setShowRegisterModal(false)}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <XMarkIcon className="h-6 w-6" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Server Name *
                  </label>
                  <input
                    type="text"
                    required
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    value={registerForm.name}
                    onChange={(e) => setRegisterForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., My Custom Server"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Path *
                  </label>
                  <input
                    type="text"
                    required
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    value={registerForm.path}
                    onChange={(e) => setRegisterForm(prev => ({ ...prev, path: e.target.value }))}
                    placeholder="/my-server"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Proxy URL *
                  </label>
                  <input
                    type="url"
                    required
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    value={registerForm.proxyPass}
                    onChange={(e) => setRegisterForm(prev => ({ ...prev, proxyPass: e.target.value }))}
                    placeholder="http://localhost:8080"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Description
                  </label>
                  <textarea
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    rows={3}
                    value={registerForm.description}
                    onChange={(e) => setRegisterForm(prev => ({ ...prev, description: e.target.value }))}
                    placeholder="Brief description of the server"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Tags
                  </label>
                  <input
                    type="text"
                    value={registerForm.tags.join(',')}
                    onChange={(e) => setRegisterForm(prev => ({ ...prev, tags: e.target.value.split(',').map(t => t.trim()).filter(t => t) }))}
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    placeholder="tag1,tag2,tag3"
                  />
                </div>
              </div>

              <div className="flex justify-end space-x-3 mt-6">
                <button
                  type="button"
                  onClick={() => setShowRegisterModal(false)}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={registerLoading}
                  className="px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-md transition-colors"
                >
                  {registerLoading ? 'Registering...' : 'Register Server'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Server Modal */}
      {editingServer && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Edit Server: {editingServer.name}
            </h3>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await handleSaveEdit();
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Server Name *
                </label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm(prev => ({ ...prev, name: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Proxy Pass URL *
                </label>
                <input
                  type="url"
                  value={editForm.proxyPass}
                  onChange={(e) => setEditForm(prev => ({ ...prev, proxyPass: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                  placeholder="http://localhost:8080"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Description
                </label>
                <textarea
                  value={editForm.description}
                  onChange={(e) => setEditForm(prev => ({ ...prev, description: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                  rows={3}
                  placeholder="Brief description of the server"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Tags
                </label>
                <input
                  type="text"
                  value={editForm.tags.join(',')}
                  onChange={(e) => setEditForm(prev => ({ ...prev, tags: e.target.value.split(',').map(t => t.trim()).filter(t => t) }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                  placeholder="tag1,tag2,tag3"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Number of Tools
                  </label>
                  <input
                    type="number"
                    value={editForm.num_tools}
                    onChange={(e) => setEditForm(prev => ({ ...prev, num_tools: parseInt(e.target.value) || 0 }))}
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    min="0"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Stars
                  </label>
                  <input
                    type="number"
                    value={editForm.num_stars}
                    onChange={(e) => setEditForm(prev => ({ ...prev, num_stars: parseInt(e.target.value) || 0 }))}
                    className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                    min="0"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  License
                </label>
                <input
                  type="text"
                  value={editForm.license}
                  onChange={(e) => setEditForm(prev => ({ ...prev, license: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-purple-500 focus:border-purple-500"
                  placeholder="MIT, Apache-2.0, etc."
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_python"
                  checked={editForm.is_python}
                  onChange={(e) => setEditForm(prev => ({ ...prev, is_python: e.target.checked }))}
                  className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                />
                <label htmlFor="is_python" className="ml-2 block text-sm text-gray-700 dark:text-gray-200">
                  Python-based server
                </label>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Path (read-only)
                </label>
                <input
                  type="text"
                  value={editForm.path}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-300"
                  disabled
                />
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="submit"
                  disabled={editLoading}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 rounded-md transition-colors"
                >
                  {editLoading ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  onClick={handleCloseEdit}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Agent Modal */}
      {editingAgent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Edit Agent: {editingAgent.name}
            </h3>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await handleSaveEditAgent();
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Agent Name *
                </label>
                <input
                  type="text"
                  value={editAgentForm.name}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, name: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Description
                </label>
                <textarea
                  value={editAgentForm.description}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, description: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                  rows={3}
                  placeholder="Brief description of the agent"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Version
                </label>
                <input
                  type="text"
                  value={editAgentForm.version}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, version: e.target.value }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                  placeholder="1.0.0"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Visibility
                </label>
                <select
                  value={editAgentForm.visibility}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, visibility: e.target.value as 'public' | 'private' | 'group-restricted' }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                >
                  <option value="private">Private</option>
                  <option value="public">Public</option>
                  <option value="group-restricted">Group Restricted</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Trust Level
                </label>
                <select
                  value={editAgentForm.trust_level}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, trust_level: e.target.value as 'community' | 'verified' | 'trusted' | 'unverified' }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                >
                  <option value="unverified">Unverified</option>
                  <option value="community">Community</option>
                  <option value="verified">Verified</option>
                  <option value="trusted">Trusted</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Tags
                </label>
                <input
                  type="text"
                  value={editAgentForm.tags.join(',')}
                  onChange={(e) => setEditAgentForm(prev => ({ ...prev, tags: e.target.value.split(',').map(t => t.trim()).filter(t => t) }))}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-cyan-500 focus:border-cyan-500"
                  placeholder="tag1,tag2,tag3"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Path (read-only)
                </label>
                <input
                  type="text"
                  value={editAgentForm.path}
                  className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-300"
                  disabled
                />
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="submit"
                  disabled={editAgentLoading}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 rounded-md transition-colors"
                >
                  {editAgentLoading ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  onClick={handleCloseEdit}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};

export default Dashboard;

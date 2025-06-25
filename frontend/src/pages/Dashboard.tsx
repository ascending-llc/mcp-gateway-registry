import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { MagnifyingGlassIcon, PlusIcon, XMarkIcon, ArrowPathIcon, CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline';
import { useServerStats } from '../hooks/useServerStats';
import { useAuth } from '../contexts/AuthContext';
import ServerCard from '../components/ServerCard';
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
  proxy_pass_url?: string;
  license?: string;
  num_stars?: number;
  is_python?: boolean;
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

const Dashboard: React.FC = () => {
  const { servers, activeFilter, loading, error, refreshData, setServers } = useServerStats();
  const { user } = useAuth();
  const [searchTerm, setSearchTerm] = useState('');
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

  // Filter servers based on activeFilter and searchTerm
  const filteredServers = useMemo(() => {
    let filtered = servers;
    
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
  }, [servers, activeFilter, searchTerm]);

  // Debug logging for server filtering
  console.log('🎯 Dashboard filtering debug:');
  console.log(`👤 Current user:`, user);
  console.log(`📊 Total servers from hook: ${servers.length}`);
  console.log(`🔍 Active filter: ${activeFilter}`);
  console.log(`🔎 Search term: "${searchTerm}"`);
  console.log(`📋 Filtered servers: ${filteredServers.length}`);

  const handleRefreshHealth = async () => {
    setRefreshing(true);
    try {
      await refreshData();
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

  const handleCloseEdit = () => {
    setEditingServer(null);
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

  // Show error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <div className="text-red-500 text-lg">Failed to load servers</div>
        <p className="text-gray-500 text-center">{error}</p>
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
  if (loading) {
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
          {/* Search Bar and Refresh Button */}
          <div className="flex gap-4 items-center">
            <div className="relative flex-1">
              <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
              </div>
              <input
                type="text"
                placeholder="Search servers, descriptions, or tags..."
                className="input pl-10 w-full"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            
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
              Showing {filteredServers.length} of {servers.length} servers
              {activeFilter !== 'all' && (
                <span className="ml-2 px-2 py-1 text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300 rounded-full">
                  {activeFilter} filter active
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {/* Server Grid */}
          {filteredServers.length === 0 ? (
            <div className="text-center py-16">
              <div className="text-gray-400 text-xl mb-4">No servers found</div>
              <p className="text-gray-500 dark:text-gray-300 text-base max-w-md mx-auto">
                {searchTerm || activeFilter !== 'all' 
                  ? 'Try adjusting your search or filter criteria' 
                  : 'No servers are registered yet'}
              </p>
              {!searchTerm && activeFilter === 'all' && (
                <button
                  onClick={handleRegisterServer}
                  className="mt-6 inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                >
                  <PlusIcon className="h-5 w-5 mr-2" />
                  Register Server
                </button>
              )}
            </div>
          ) : (
            <div 
              className="grid auto-rows-fr pb-12"
              style={{ 
                gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))',
                gap: 'clamp(1.5rem, 3vw, 2.5rem)',
                minHeight: '70vh'
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
                />
              ))}
            </div>
          )}
        </div>
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
    </>
  );
};

export default Dashboard; 
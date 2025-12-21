import React, { Fragment, useEffect, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { Link, useLocation } from 'react-router-dom';
import {
  XMarkIcon,
  FunnelIcon,
  ChartBarIcon,
  KeyIcon,
  ArrowLeftIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClipboardIcon,
  CheckIcon,
  ArrowDownTrayIcon
} from '@heroicons/react/24/outline';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';

interface SidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  stats: {
    total: number;
    enabled: number;
    disabled: number;
    withIssues: number;
  };
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
}


const Sidebar: React.FC<SidebarProps> = ({ sidebarOpen, setSidebarOpen, stats, activeFilter, setActiveFilter }) => {
  // const { stats, activeFilter, setActiveFilter } = useServerStats();
  const { user } = useAuth();
  const location = useLocation();
  const [showScopes, setShowScopes] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [tokenData, setTokenData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string>('');

  const filters = [
    { key: 'all', label: 'All Services', count: 'total' },
    { key: 'enabled', label: 'Enabled', count: 'enabled' },
    { key: 'disabled', label: 'Disabled', count: 'disabled' },
    { key: 'unhealthy', label: 'With Issues', count: 'withIssues' },
  ];

  const isTokenPage = location.pathname === '/generate-token';

  // Debug logging
  useEffect(() => {
    console.log('Sidebar state changed:', sidebarOpen);
  }, [sidebarOpen]);

  // Scope descriptions mapping
  const getScopeDescription = (scope: string) => {
    const scopeMappings: { [key: string]: string } = {
      'mcp-servers-restricted/read': 'Read access to restricted MCP servers',
      'mcp-servers/read': 'Read access to all MCP servers',
      'mcp-servers/write': 'Write access to MCP servers',
      'mcp-registry-user': 'Basic registry user permissions',
      'mcp-registry-admin': 'Full registry administration access',
      'health-check': 'Health check and monitoring access',
      'token-generation': 'Ability to generate access tokens',
      'server-management': 'Manage server configurations',
    };
    return scopeMappings[scope] || 'Custom permission scope';
  };

const fetchAdminTokens = async () => {
  setLoading(true);
  setError('');
  try {
    const requestData = {
      description: 'Generated via sidebar',
      expires_in_hours: 8,
    };
    
    const response = await axios.post('/api/tokens/generate', requestData, {
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    if (response.data.success) {
      setTokenData(response.data);
      setShowTokenModal(true);
    }
  } catch (err: any) {
    setError(err.response?.data?.detail || 'Failed to generate token');
  } finally {
    setLoading(false);
  }
};


  const handleCopyTokens = async () => {
    if (!tokenData) return;

    const formattedData = JSON.stringify(tokenData, null, 2);
    try {
      await navigator.clipboard.writeText(formattedData);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleDownloadTokens = () => {
    if (!tokenData) return;

    const formattedData = JSON.stringify(tokenData, null, 2);
    const blob = new Blob([formattedData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mcp-registry-api-tokens-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      {/* Conditional Content */}
      {isTokenPage ? (
        /* Token Page - Show navigation and user info */
        <div className="flex-1 p-4 md:p-6">
          {/* Navigation Links */}
          <div className="space-y-2 mb-6">
            <Link
              to="/"
              className="flex items-center space-x-3 px-3 py-2 rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              onClick={() => window.innerWidth < 768 && setSidebarOpen(false)} // Only close on mobile
              tabIndex={0}
            >
              <ArrowLeftIcon className="h-4 w-4" />
              <span>Back to Dashboard</span>
            </Link>
            
            <Link
              to="/generate-token"
              className="flex items-center space-x-3 px-3 py-2 rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300"
              tabIndex={0}
            >
              <KeyIcon className="h-4 w-4" />
              <span>Generate Token</span>
            </Link>
          </div>

          {/* User Access Information */}
          {user && (
            <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg mb-6">
              <div className="text-sm">
                <div className="font-medium text-gray-900 dark:text-white mb-1">
                  {user.username}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-300 mb-2">
                  {user.is_admin ? (
                    <span className="text-green-600 dark:text-green-400">🔑 Admin Access</span>
                  ) : user.can_modify_servers ? (
                    <span className="text-blue-600 dark:text-blue-400">⚙️ Modify Access</span>
                  ) : (
                    <span className="text-gray-600 dark:text-gray-300">👁️ Read-only Access</span>
                  )}
                  {user.auth_method === 'oauth2' && user.provider && (
                    <span className="ml-1">({user.provider})</span>
                  )}
                </div>
                
                {/* Scopes toggle */}
                {!user.is_admin && user.scopes && user.scopes.length > 0 && (
                  <div>
                    <button
                      onClick={() => setShowScopes(!showScopes)}
                      className="flex items-center justify-between w-full text-xs text-gray-500 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-100 transition-colors py-1"
                    >
                      <span>Scopes ({user.scopes.length})</span>
                      {showScopes ? (
                        <ChevronUpIcon className="h-3 w-3" />
                      ) : (
                        <ChevronDownIcon className="h-3 w-3" />
                      )}
                    </button>
                    
                    {showScopes && (
                      <div className="mt-2 space-y-2 max-h-32 overflow-y-auto">
                        {user.scopes.map((scope) => (
                          <div key={scope} className="bg-blue-50 dark:bg-blue-900/20 p-2 rounded text-xs">
                            <div className="font-medium text-blue-800 dark:text-blue-200">
                              {scope}
                            </div>
                            <div className="text-blue-600 dark:text-blue-300 mt-1">
                              {getScopeDescription(scope)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Token Generation Help */}
          <div className="text-center">
            <KeyIcon className="h-12 w-12 text-purple-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Token Generation</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Create personal access tokens for programmatic access to MCP servers
            </p>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
              <p>• Tokens inherit your current permissions</p>
              <p>• Configure expiration time and scopes</p>
              <p>• Use tokens for programmatic access</p>
            </div>
          </div>
        </div>
      ) : (
        /* Dashboard - Show user info, filters and stats */
        <>
          {/* User Info Header */}
          <div className="p-4 md:p-6 border-b border-gray-200 dark:border-gray-700">
            {/* User Access Information */}
            {user && (
              <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div className="text-sm">
                  <div className="font-medium text-gray-900 dark:text-white mb-1">
                    {user.username}
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-300 mb-2">
                    {user.is_admin ? (
                      <span className="text-green-600 dark:text-green-400">🔑 Admin Access</span>
                    ) : user.can_modify_servers ? (
                      <span className="text-blue-600 dark:text-blue-400">⚙️ Modify Access</span>
                    ) : (
                      <span className="text-gray-600 dark:text-gray-300">👁️ Read-only Access</span>
                    )}
                    {user.auth_method === 'oauth2' && user.provider && (
                      <span className="ml-1">({user.provider})</span>
                    )}
                  </div>

                  {/* Admin JWT Token Button */}
                  {user.is_admin && (
                    <div className="mb-2">
                      <button
                        onClick={fetchAdminTokens}
                        disabled={loading}
                        className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-800 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {loading ? (
                          <>
                            <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-purple-700 dark:border-purple-300"></div>
                            <span>Loading...</span>
                          </>
                        ) : (
                          <>
                            <KeyIcon className="h-3 w-3" />
                            <span>Get JWT Token</span>
                          </>
                        )}
                      </button>
                      {error && (
                        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
                      )}
                    </div>
                  )}

                  {/* Scopes toggle */}
                  {!user.is_admin && user.scopes && user.scopes.length > 0 && (
                    <div>
                      <button
                        onClick={() => setShowScopes(!showScopes)}
                        className="flex items-center justify-between w-full text-xs text-gray-500 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-100 transition-colors py-1"
                      >
                        <span>Scopes ({user.scopes.length})</span>
                        {showScopes ? (
                          <ChevronUpIcon className="h-3 w-3" />
                        ) : (
                          <ChevronDownIcon className="h-3 w-3" />
                        )}
                      </button>

                      {showScopes && (
                        <div className="mt-2 space-y-2 max-h-32 overflow-y-auto">
                          {user.scopes.map((scope) => (
                            <div key={scope} className="bg-blue-50 dark:bg-blue-900/20 p-2 rounded text-xs">
                              <div className="font-medium text-blue-800 dark:text-blue-200">
                                {scope}
                              </div>
                              <div className="text-blue-600 dark:text-blue-300 mt-1">
                                {getScopeDescription(scope)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Filters Section */}
          <div className="flex-1 p-4 md:p-6">
            <div className="flex items-center space-x-2 mb-4">
              <FunnelIcon className="h-4 w-4 text-gray-600 dark:text-gray-400" />
              <h3 className="text-sm font-medium text-gray-900 dark:text-white">Filter Services</h3>
            </div>
            
            <div className="space-y-2">
              {filters.map((filter) => (
                <button
                  key={filter.key}
                  onClick={() => setActiveFilter(filter.key)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-500 ${
                    activeFilter === filter.key
                      ? 'bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-800'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                  tabIndex={0}
                >
                  <div className="flex items-center justify-between">
                    <span>{filter.label}</span>
                    <span className="text-xs bg-gray-200 dark:bg-gray-700 px-2 py-1 rounded-full">
                      {stats[filter.count as keyof typeof stats]}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Statistics Section */}
          <div className="border-t border-gray-200 dark:border-gray-700 p-4 md:p-6">
            <div className="flex items-center space-x-2 mb-4">
              <ChartBarIcon className="h-5 w-5 text-gray-500" />
              <h3 className="text-sm font-medium text-gray-900 dark:text-white">Statistics</h3>
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div className="text-xl font-semibold text-gray-900 dark:text-white">{stats.total}</div>
                <div className="text-xs text-gray-500 dark:text-gray-300">Total</div>
              </div>
              <div className="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <div className="text-xl font-semibold text-green-600 dark:text-green-400">{stats.enabled}</div>
                <div className="text-xs text-green-600 dark:text-green-400">Enabled</div>
              </div>
              <div className="text-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div className="text-xl font-semibold text-gray-500 dark:text-gray-300">{stats.disabled}</div>
                <div className="text-xs text-gray-500 dark:text-gray-300">Disabled</div>
              </div>
              <div className="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                <div className="text-xl font-semibold text-red-600 dark:text-red-400">{stats.withIssues}</div>
                <div className="text-xs text-red-600 dark:text-red-400">Issues</div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <>
      {/* Mobile sidebar only */}
      {window.innerWidth < 768 && (
        <Transition.Root show={sidebarOpen} as={Fragment}>
          <Dialog as="div" className="relative z-50" onClose={setSidebarOpen}>
            <Transition.Child
              as={Fragment}
              enter="transition-opacity ease-linear duration-300"
              enterFrom="opacity-0"
              enterTo="opacity-100"
              leave="transition-opacity ease-linear duration-300"
              leaveFrom="opacity-100"
              leaveTo="opacity-0"
            >
              <div className="fixed inset-0 bg-gray-900/80" />
            </Transition.Child>

            <div className="fixed inset-0 flex">
              <Transition.Child
                as={Fragment}
                enter="transition ease-in-out duration-300 transform"
                enterFrom="-translate-x-full"
                enterTo="translate-x-0"
                leave="transition ease-in-out duration-300 transform"
                leaveFrom="translate-x-0"
                leaveTo="-translate-x-full"
              >
                <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
                  <Transition.Child
                    as={Fragment}
                    enter="ease-in-out duration-300"
                    enterFrom="opacity-0"
                    enterTo="opacity-100"
                    leave="ease-in-out duration-300"
                    leaveFrom="opacity-100"
                    leaveTo="opacity-0"
                  >
                    <div className="absolute left-full top-0 flex w-16 justify-center pt-5">
                      <button
                        type="button"
                        className="-m-2.5 p-2.5"
                        onClick={() => setSidebarOpen(false)}
                        aria-label="Close sidebar"
                      >
                        <XMarkIcon className="h-6 w-6 text-white" />
                      </button>
                    </div>
                  </Transition.Child>
                  
                  <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
                    <SidebarContent />
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </Dialog>
        </Transition.Root>
      )}

      {/* Desktop sidebar only */}
      {window.innerWidth >= 768 && (
        <Transition show={sidebarOpen} as={Fragment}>
          <Transition.Child
            as={Fragment}
            enter="transition ease-in-out duration-300 transform"
            enterFrom="-translate-x-full"
            enterTo="translate-x-0"
            leave="transition ease-in-out duration-300 transform"
            leaveFrom="translate-x-0"
            leaveTo="-translate-x-full"
          >
            <div className="fixed left-0 top-16 bottom-0 z-40 w-64 lg:w-72 xl:w-80 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
              <SidebarContent />
            </div>
          </Transition.Child>
        </Transition>
      )}

      {/* Token Modal */}
      <Transition appear show={showTokenModal} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={() => setShowTokenModal(false)}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black bg-opacity-25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-3xl transform overflow-hidden rounded-2xl bg-white dark:bg-gray-800 p-6 text-left align-middle shadow-xl transition-all">
                  <Dialog.Title
                    as="h3"
                    className="text-lg font-medium leading-6 text-gray-900 dark:text-white mb-4"
                  >
                    Keycloak Admin Tokens
                  </Dialog.Title>

                  {tokenData && (
                    <div className="space-y-4">
                      {/* Action Buttons */}
                      <div className="flex space-x-2">
                        <button
                          onClick={handleCopyTokens}
                          className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
                        >
                          {copied ? (
                            <>
                              <CheckIcon className="h-4 w-4" />
                              <span>Copied!</span>
                            </>
                          ) : (
                            <>
                              <ClipboardIcon className="h-4 w-4" />
                              <span>Copy JSON</span>
                            </>
                          )}
                        </button>
                        <button
                          onClick={handleDownloadTokens}
                          className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm"
                        >
                          <ArrowDownTrayIcon className="h-4 w-4" />
                          <span>Download JSON</span>
                        </button>
                      </div>

                      {/* Token Data Display */}
                      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 max-h-96 overflow-y-auto">
                        <pre className="text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-all">
                          {JSON.stringify(tokenData, null, 2)}
                        </pre>
                      </div>

                      {/* Close Button */}
                      <div className="flex justify-end">
                        <button
                          onClick={() => setShowTokenModal(false)}
                          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm"
                        >
                          Close
                        </button>
                      </div>
                    </div>
                  )}
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </>
  );
};

export default Sidebar; 
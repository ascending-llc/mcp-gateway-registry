import { PencilIcon, WrenchScrewdriverIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useGlobal } from '@/contexts/GlobalContext';
import { useServer } from '@/contexts/ServerContext';
import SERVICES from '@/services';
import type { Agent } from '@/services/agent/type';

/**
 * Props for the AgentCard component.
 */
interface AgentCardProps {
  agent: Agent & { [key: string]: any }; // Allow additional fields from full agent JSON
}

/**
 * AgentCard component for displaying A2A agents.
 */
const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const navigate = useNavigate();
  const { showToast } = useGlobal();
  const { handleAgentUpdate } = useServer();
  const [loading, setLoading] = useState(false);

  const toEditPage = async (agent: Agent) => {
    navigate(`/agent-edit?id=${(agent as any).id || agent.path}`);
  };

  const handleToggleAgent = async (id: string, enabled: boolean) => {
    try {
      setLoading(true);
      await SERVICES.AGENT.toggleAgentState(id, { enabled });
      handleAgentUpdate(id, { enabled });
      showToast(`Agent ${enabled ? 'enabled' : 'disabled'} successfully!`, 'success');
    } catch (error: any) {
      const errorMessage = error.detail?.message || (typeof error.detail === 'string' ? error.detail : '');
      showToast(errorMessage || 'Failed to toggle agent', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className='group rounded-2xl shadow-sm hover:shadow-xl transition-all duration-300 h-full flex flex-col relative bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 hover:border-gray-200 dark:hover:border-gray-600'>
        {loading && (
          <div className='absolute inset-0 bg-white/20 dark:bg-black/20 backdrop-blur-sm rounded-2xl flex items-center justify-center z-10'>
            <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600'></div>
          </div>
        )}

        {/* Header */}
        <div className='p-4 pb-3'>
          <div className='flex items-start justify-between mb-3'>
            <div className='flex-1 min-w-0'>
              <div className='flex flex-wrap items-center gap-1.5 mb-2'>
                {agent.permissions?.VIEW ? (
                  <h3
                    className='text-base font-bold text-gray-900 dark:text-white truncate max-w-[160px] cursor-pointer hover:text-purple-600 dark:hover:text-purple-400 transition-colors'
                    onClick={() => navigate(`/agent-edit?id=${agent.id}&isReadOnly=true`)}
                  >
                    {agent.name}
                  </h3>
                ) : (
                  <h3 className='text-base font-bold text-gray-900 dark:text-white truncate max-w-[160px]'>
                    {agent.name}
                  </h3>
                )}
              </div>
            </div>

            <div className='flex gap-1'>
              {agent.permissions?.EDIT && (
                <button
                  className='p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded-lg transition-all duration-200 flex-shrink-0'
                  onClick={() => toEditPage?.(agent)}
                  title='Edit agent'
                >
                  <PencilIcon className='h-3.5 w-3.5' />
                </button>
              )}
            </div>
          </div>

          {/* Description */}
          <p className='text-gray-600 dark:text-gray-300 text-xs leading-relaxed line-clamp-2 mb-3'>
            {agent.description || 'No description available'}
          </p>

          {/* Tags */}
          {agent.tags && agent.tags.length > 0 && (
            <div className='flex flex-wrap gap-1 mb-3 max-h-10 overflow-hidden'>
              {agent.tags.slice(0, 3).map(tag => (
                <span
                  key={tag}
                  className='px-1.5 py-0.5 text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded truncate max-w-[100px]'
                >
                  #{tag}
                </span>
              ))}
              {agent.tags.length > 3 && (
                <span className='px-1.5 py-0.5 text-xs font-medium bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded'>
                  +{agent.tags.length - 3}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Skills */}
        <div className='px-4 pb-3'>
          <div className='grid grid-cols-2 gap-2'>
            <div className='flex items-center gap-1.5'>
              {(agent.skills?.length || 0) > 0 ? (
                <div className='flex items-center gap-1.5 text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 px-1.5 py-0.5 -mx-1.5 -my-0.5 rounded transition-all text-xs'>
                  <div className='p-1 bg-blue-50 dark:bg-blue-900/30 rounded'>
                    <WrenchScrewdriverIcon className='h-3.5 w-3.5' />
                  </div>
                  <div>
                    <div className='text-xs font-semibold'>{agent.skills.length}</div>
                    <div className='text-xs'>Skills</div>
                  </div>
                </div>
              ) : (
                <div className='flex items-center gap-1.5 text-gray-400 dark:text-gray-500'>
                  <div className='p-1 bg-gray-50 dark:bg-gray-800 rounded'>
                    <WrenchScrewdriverIcon className='h-3.5 w-3.5' />
                  </div>
                  <div>
                    <div className='text-xs font-semibold'>0</div>
                    <div className='text-xs'>Skills</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className='mt-auto px-3 py-3 border-t border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/30 rounded-b-2xl'>
          <div className='flex flex-col sm:flex-row items-center justify-between gap-1'>
            <div className='flex items-center gap-2 flex-wrap justify-center'>
              {/* Status Indicators */}
              <div className='flex items-center gap-1'>
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    agent.enabled ? 'bg-green-400 shadow-lg shadow-green-400/30' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                />
                <span className='text-xs font-medium text-gray-700 dark:text-gray-300'>
                  {agent.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>

              <div className='w-px h-3 bg-gray-200 dark:bg-gray-600' />

              <div className='flex items-center gap-1'>
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    agent.status === 'active'
                      ? 'bg-emerald-400 shadow-lg shadow-emerald-400/30'
                      : agent.status === 'inactive'
                        ? 'bg-orange-400 shadow-lg shadow-orange-400/30'
                        : agent.status === 'error'
                          ? 'bg-red-400 shadow-lg shadow-red-400/30'
                          : 'bg-amber-400 shadow-lg shadow-amber-400/30'
                  }`}
                />
                <span className='text-xs font-medium text-gray-700 dark:text-gray-300 max-w-[80px] truncate'>
                  {agent.status === 'active'
                    ? 'Active'
                    : agent.status === 'inactive'
                      ? 'Inactive'
                      : agent.status === 'error'
                        ? 'Error'
                        : 'Unknown'}
                </span>
              </div>
            </div>

            {/* Controls */}
            <div className='flex items-center gap-2'>
              {/* Toggle Switch */}
              <label className='relative inline-flex items-center cursor-pointer' onClick={e => e.stopPropagation()}>
                <input
                  type='checkbox'
                  checked={agent.enabled}
                  className='sr-only peer'
                  onChange={e => {
                    e.stopPropagation();
                    handleToggleAgent(agent.id, e.target.checked);
                  }}
                />
                <div
                  className={`relative w-7 h-4 rounded-full transition-colors duration-200 ease-in-out ${
                    agent.enabled ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 left-0 w-3 h-3 bg-white rounded-full transition-transform duration-200 ease-in-out ${
                      agent.enabled ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </div>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentCard;

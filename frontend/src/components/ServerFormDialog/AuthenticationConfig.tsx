import { EyeIcon, EyeSlashIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useState } from 'react';
import type { AuthenticationConfig as AuthConfigType } from './types';

interface AuthenticationConfigProps {
  config: AuthConfigType;
  onChange: (config: AuthConfigType) => void;
  errors?: Record<string, string | undefined>;
}

const AuthenticationConfig: React.FC<AuthenticationConfigProps> = ({ config, onChange, errors = {} }) => {
  const [showApiKey, setShowApiKey] = useState(false);
  const [showClientSecret, setShowClientSecret] = useState(false);

  const updateConfig = (updates: Partial<AuthConfigType>) => {
    onChange({ ...config, ...updates });
  };

  const getInputClass = (fieldName: string) => {
    const baseClass =
      'block w-full rounded-md shadow-sm focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500';
    const borderClass = errors[fieldName]
      ? 'border-red-500 focus:border-red-500 pr-10' // Add padding for icon if needed, though error message is below
      : 'border-gray-300 dark:border-gray-600 focus:border-purple-500';
    return `${baseClass} ${borderClass}`;
  };

  const renderError = (fieldName: string) => {
    if (!errors[fieldName]) return null;
    return <p className='mt-1 text-xs text-red-500'>{errors[fieldName]}</p>;
  };

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-4'>Authentication</h3>

        <div className='space-y-4'>
          <div>
            <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>
              Authentication Type
            </label>
            <div className='flex p-1 bg-gray-200 dark:bg-gray-700/50 rounded-lg'>
              <button
                type='button'
                onClick={() => updateConfig({ type: 'auto' })}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                  config.type === 'auto'
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                No Auth
              </button>
              <button
                type='button'
                onClick={() => updateConfig({ type: 'apiKey' })}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                  config.type === 'apiKey'
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                API Key
              </button>
              <button
                type='button'
                onClick={() => updateConfig({ type: 'oauth' })}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                  config.type === 'oauth'
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                OAuth
              </button>
            </div>
          </div>

          {config.type === 'auto' && (
            <div className='rounded-md bg-gray-50 dark:bg-gray-700/50 p-4 text-sm text-gray-600 dark:text-gray-300'>
              DCR will be attempted if auth is required. Choose this if your MCP server has no auth requirements or
              supports DCR.
            </div>
          )}

          {config.type === 'apiKey' && (
            <div className='space-y-4 animate-fadeIn'>
              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>
                  API Key Source
                </label>
                <div className='flex items-center space-x-2'>
                  <input
                    type='checkbox'
                    id='apiKeySource'
                    checked={config.source === 'user'}
                    onChange={e => updateConfig({ source: e.target.checked ? 'user' : 'admin' })}
                    className='h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700'
                  />
                  <label htmlFor='apiKeySource' className='text-sm text-gray-900 dark:text-gray-100'>
                    Each user provides their own key
                    <span className='block text-xs text-gray-500 dark:text-gray-400'>
                      When unchecked, an admin-provided key is used for all users.
                    </span>
                  </label>
                </div>
              </div>

              {config.source === 'admin' && (
                <div>
                  <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>API Key</label>
                  <div className='relative rounded-md shadow-sm'>
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      className={`${getInputClass('key')} pr-10`}
                      placeholder='sk-...'
                      value={config.key || ''}
                      onChange={e => updateConfig({ key: e.target.value })}
                    />
                    <button
                      type='button'
                      onClick={() => setShowApiKey(!showApiKey)}
                      className='absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400 focus:outline-none'
                    >
                      {showApiKey ? (
                        <EyeSlashIcon className='h-5 w-5' aria-hidden='true' />
                      ) : (
                        <EyeIcon className='h-5 w-5' aria-hidden='true' />
                      )}
                    </button>
                  </div>
                  {renderError('key')}
                </div>
              )}

              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>Header Format</label>
                <div className='flex p-1 bg-gray-200 dark:bg-gray-700/50 rounded-lg'>
                  <button
                    type='button'
                    onClick={() => updateConfig({ authorization_type: 'bearer' })}
                    className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                      config.authorization_type === 'bearer'
                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                    }`}
                  >
                    Bearer
                  </button>
                  <button
                    type='button'
                    onClick={() => updateConfig({ authorization_type: 'basic' })}
                    className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                      config.authorization_type === 'basic'
                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                    }`}
                  >
                    Basic
                  </button>
                  <button
                    type='button'
                    onClick={() => updateConfig({ authorization_type: 'custom' })}
                    className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                      config.authorization_type === 'custom'
                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                    }`}
                  >
                    Custom
                  </button>
                </div>

                {config.authorization_type === 'custom' && (
                  <div className='mt-4 animate-fadeIn'>
                    <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>
                      Custom Header Name <span className='text-red-500'>*</span>
                    </label>
                    <input
                      type='text'
                      required
                      className={getInputClass('custom_header')}
                      value={config.custom_header || ''}
                      onChange={e => updateConfig({ custom_header: e.target.value })}
                      placeholder='X-Custom-Auth'
                    />
                    {renderError('custom_header')}
                  </div>
                )}
              </div>
            </div>
          )}

          {config.type === 'oauth' && (
            <div className='space-y-4 animate-fadeIn'>
              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>
                  Client ID <span className='text-red-500'>*</span>
                </label>
                <input
                  type='text'
                  required
                  className={getInputClass('client_id')}
                  value={config.client_id || ''}
                  onChange={e => updateConfig({ client_id: e.target.value })}
                />
                {renderError('client_id')}
              </div>
              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>
                  Client Secret <span className='text-red-500'>*</span>
                </label>
                <div className='relative rounded-md shadow-sm'>
                  <input
                    type={showClientSecret ? 'text' : 'password'}
                    required
                    className={`${getInputClass('client_secret')} pr-10`}
                    value={config.client_secret || ''}
                    onChange={e => updateConfig({ client_secret: e.target.value })}
                  />
                  <button
                    type='button'
                    onClick={() => setShowClientSecret(!showClientSecret)}
                    className='absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400 focus:outline-none'
                  >
                    {showClientSecret ? (
                      <EyeSlashIcon className='h-5 w-5' aria-hidden='true' />
                    ) : (
                      <EyeIcon className='h-5 w-5' aria-hidden='true' />
                    )}
                  </button>
                </div>
                {renderError('client_secret')}
              </div>
              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>
                  Authorization URL <span className='text-red-500'>*</span>
                </label>
                <input
                  type='url'
                  required
                  className={getInputClass('authorization_url')}
                  value={config.authorization_url || ''}
                  onChange={e => updateConfig({ authorization_url: e.target.value })}
                />
                {renderError('authorization_url')}
              </div>
              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>
                  Token URL <span className='text-red-500'>*</span>
                </label>
                <input
                  type='url'
                  required
                  className={getInputClass('token_url')}
                  value={config.token_url || ''}
                  onChange={e => updateConfig({ token_url: e.target.value })}
                />
                {renderError('token_url')}
              </div>

              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>Scope</label>
                <input
                  type='text'
                  className={getInputClass('scope')}
                  value={config.scope || ''}
                  onChange={e => updateConfig({ scope: e.target.value })}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AuthenticationConfig;

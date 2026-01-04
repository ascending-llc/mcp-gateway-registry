import React, { useState, useEffect } from 'react';

import { AuthenticationConfig as AuthConfigType, AuthType, ApiKeySource, ApiKeyHeaderFormat } from './types';

interface AuthenticationConfigProps {
  config: AuthConfigType;
  onChange: (config: AuthConfigType) => void;
  onCancel: () => void;
  onSave: () => void;
}

const AuthenticationConfig: React.FC<AuthenticationConfigProps> = ({
  config: initialConfig,
  onChange,
  onCancel,
  onSave,
}) => {
  const [localConfig, setLocalConfig] = useState<AuthConfigType>(initialConfig);

  const updateConfig = (updates: Partial<AuthConfigType>) => {
    setLocalConfig((prev) => ({ ...prev, ...updates }));
  };

  const handleSave = () => {
    onChange(localConfig);
    onSave();
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Authentication</h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Authentication Type</label>
            <div className="flex items-center space-x-6">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="auto"
                  checked={localConfig.type === 'auto'}
                  onChange={() => updateConfig({ type: 'auto' })}
                  className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                />
                <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Auto Detect</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="api-key"
                  checked={localConfig.type === 'api-key'}
                  onChange={() => updateConfig({ type: 'api-key' })}
                  className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                />
                <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">API Key</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="authType"
                  value="oauth"
                  checked={localConfig.type === 'oauth'}
                  onChange={() => updateConfig({ type: 'oauth' })}
                  className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                />
                <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Manual OAuth</span>
              </label>
            </div>
          </div>

          {localConfig.type === 'auto' && (
             <div className="rounded-md bg-gray-50 dark:bg-gray-700/50 p-4 text-sm text-gray-600 dark:text-gray-300">
               DCR will be attempted if auth is required. Choose this if your MCP server has no auth requirements or supports DCR.
             </div>
          )}

          {localConfig.type === 'api-key' && (
            <div className="space-y-4 animate-fadeIn">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">API Key Source</label>
                <div className="space-y-2">
                   <label className="flex items-center">
                    <input
                      type="radio"
                      name="apiKeySource"
                      value="global"
                      checked={localConfig.apiKeySource === 'global'}
                      onChange={() => updateConfig({ apiKeySource: 'global' })}
                      className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Provide a key for all users</span>
                  </label>
                   <label className="flex items-center">
                    <input
                      type="radio"
                      name="apiKeySource"
                      value="user"
                      checked={localConfig.apiKeySource === 'user'}
                      onChange={() => updateConfig({ apiKeySource: 'user' })}
                      className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Each user provides their own key</span>
                  </label>
                </div>
              </div>

               {localConfig.apiKeySource === 'global' && (
                <div>
                   <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">API Key</label>
                   <div className="relative rounded-md shadow-sm">
                      <input
                        type="password"
                        className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                        placeholder="<HIDDEN>"
                        value={localConfig.apiKey || ''}
                        onChange={(e) => updateConfig({ apiKey: e.target.value })}
                      />
                   </div>
                </div>
               )}

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Header Format</label>
                 <div className="flex items-center space-x-6">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="headerFormat"
                      value="bearer"
                      checked={localConfig.headerFormat === 'bearer'}
                      onChange={() => updateConfig({ headerFormat: 'bearer' })}
                      className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Bearer</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="headerFormat"
                      value="basic"
                      checked={localConfig.headerFormat === 'basic'}
                      onChange={() => updateConfig({ headerFormat: 'basic' })}
                      className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Basic</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="headerFormat"
                      value="custom"
                      checked={localConfig.headerFormat === 'custom'}
                      onChange={() => updateConfig({ headerFormat: 'custom' })}
                      className="h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-900 dark:text-gray-100">Custom</span>
                  </label>
                 </div>
              </div>
            </div>
          )}

          {localConfig.type === 'oauth' && (
            <div className="space-y-4 animate-fadeIn">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Client ID <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  required
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                  value={localConfig.clientId || ''}
                  onChange={(e) => updateConfig({ clientId: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Client Secret <span className="text-red-500">*</span></label>
                 <div className="relative">
                  <input
                    type="password"
                    required
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                    value={localConfig.clientSecret || ''}
                    onChange={(e) => updateConfig({ clientSecret: e.target.value })}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Authorization URL <span className="text-red-500">*</span></label>
                <input
                  type="url"
                  required
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                  value={localConfig.authorizationUrl || ''}
                  onChange={(e) => updateConfig({ authorizationUrl: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Token URL <span className="text-red-500">*</span></label>
                <input
                  type="url"
                  required
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                  value={localConfig.tokenUrl || ''}
                  onChange={(e) => updateConfig({ tokenUrl: e.target.value })}
                />
              </div>

               <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Redirect URI</label>
                 <div className="block w-full rounded-md bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 p-3 text-sm text-gray-500 dark:text-gray-400">
                    The redirect URI will be provided after the server is created. Configure it in your OAuth provider settings.
                 </div>
              </div>

               <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">Scope</label>
                <input
                  type="text"
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
                  value={localConfig.scope || ''}
                  onChange={(e) => updateConfig({ scope: e.target.value })}
                />
              </div>
            </div>
          )}
        </div>
      </div>

       <div className="flex justify-end space-x-3 pt-6 border-t border-gray-100 dark:border-gray-700 mt-6">
        <button
          onClick={onCancel}
          className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-700 hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500"
        >
          Save
        </button>
      </div>
    </div>
  );
};

export default AuthenticationConfig;

import { ClipboardDocumentIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useState } from 'react';
import FormFields from '@/components/FormFields';
import { getBasePath } from '@/config';
import type { AuthenticationConfig as AuthConfigType } from './types';

interface AuthenticationConfigProps {
  config: AuthConfigType;
  isEditMode?: boolean;
  onChange: (config: AuthConfigType) => void;
  errors?: Record<string, string | undefined>;
  isReadOnly?: boolean;
  path?: string;
}

const AuthenticationConfig: React.FC<AuthenticationConfigProps> = ({
  config,
  isEditMode = false,
  onChange,
  errors = {},
  isReadOnly = false,
  path = '',
}) => {
  const [isApiKeyDirty, setIsApiKeyDirty] = useState(false);
  const [isClientSecretDirty, setIsClientSecretDirty] = useState(false);

  const updateConfig = (updates: Partial<AuthConfigType>) => {
    onChange({ ...config, ...updates });
  };

  const cleanPath = path?.replace(/\/+$/, '') || '';
  const serverPath = cleanPath && !cleanPath.startsWith('/') ? `/${cleanPath}` : cleanPath;
  const redirectUri = `${window.location.protocol}//${window.location.host}${getBasePath()}/api/v1/mcp${serverPath}/oauth/callback`;

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Authentication</h3>
        <div className='space-y-4'>
          <div>
            <FormFields.RadioGroupField
              label='Authentication Type'
              value={config.type}
              onChange={val => updateConfig({ type: val })}
              options={[
                { label: 'No Auth', value: 'auto' },
                { label: 'API Key', value: 'apiKey' },
                { label: 'OAuth', value: 'oauth' },
              ]}
              disabled={isReadOnly}
            />
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
                <FormFields.CheckboxField
                  id='apiKeySource'
                  disabled={isReadOnly}
                  checked={config.source === 'user'}
                  onChange={e => updateConfig({ source: e.target.checked ? 'user' : 'admin' })}
                  label='Each user provides their own key'
                  description='When unchecked, an admin-provided key is used for all users.'
                />
              </div>

              {config.source === 'admin' && (
                <FormFields.InputField
                  label='API Key'
                  type='password'
                  showPasswordToggle={!isEditMode || isApiKeyDirty}
                  monospace
                  disabled={isReadOnly}
                  value={isEditMode && !isApiKeyDirty ? '' : config.key || ''}
                  placeholder={isEditMode && !isApiKeyDirty && config.key ? config.key : '...'}
                  onChange={e => {
                    setIsApiKeyDirty(true);
                    updateConfig({ key: e.target.value });
                  }}
                  helperText='Leave empty if using OAuth or no authentication'
                  error={errors.key}
                />
              )}

              <div>
                <FormFields.RadioGroupField
                  label='Header Format'
                  value={config.authorization_type || 'bearer'}
                  onChange={val => updateConfig({ authorization_type: val })}
                  options={[
                    { label: 'Bearer', value: 'bearer' },
                    { label: 'Basic', value: 'basic' },
                    { label: 'Custom', value: 'custom' },
                  ]}
                  disabled={isReadOnly}
                />

                {config.authorization_type === 'custom' && (
                  <div className='mt-4 animate-fadeIn'>
                    <FormFields.InputField
                      label='Custom Header Name'
                      required
                      disabled={isReadOnly}
                      value={config.custom_header || ''}
                      onChange={e => updateConfig({ custom_header: e.target.value })}
                      placeholder='X-Custom-Auth'
                      error={errors.custom_header}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {config.type === 'oauth' && (
            <div className='space-y-4 animate-fadeIn'>
              <FormFields.InputField
                label='Client ID'
                disabled={isReadOnly}
                placeholder='your-client-id-here'
                value={config.client_id || ''}
                onChange={e => updateConfig({ client_id: e.target.value })}
                helperText='Required for static clients. Leave blank if using dynamic client registration'
                error={errors.client_id}
              />

              <FormFields.InputField
                label='Client Secret'
                type='password'
                showPasswordToggle={!isEditMode || isClientSecretDirty}
                monospace
                disabled={isReadOnly}
                value={isEditMode && !isClientSecretDirty ? '' : config.client_secret || ''}
                placeholder={
                  isEditMode && !isClientSecretDirty && config.client_secret
                    ? config.client_secret
                    : 'your-client-secret-here'
                }
                onChange={e => {
                  setIsClientSecretDirty(true);
                  updateConfig({ client_secret: e.target.value });
                }}
                helperText='Required for static clients. Never share this value.'
                error={errors.client_secret}
              />

              <FormFields.InputField
                label='Authorization URL'
                required
                type='url'
                disabled={isReadOnly}
                placeholder='https://auth.example.com/oauth/authorize'
                value={config.authorization_url || ''}
                onChange={e => updateConfig({ authorization_url: e.target.value })}
                helperText='The endpoint where users are redirected to authenticate and grant permissions.'
                error={errors.authorization_url}
              />

              <FormFields.InputField
                label='Token URL'
                required
                type='url'
                disabled={isReadOnly}
                placeholder='https://auth.example.com/oauth/token'
                value={config.token_url || ''}
                onChange={e => updateConfig({ token_url: e.target.value })}
                helperText='The backend endpoint for exchanging authorization codes for access tokens.'
                error={errors.token_url}
              />

              <FormFields.InputField
                label='Scope'
                disabled={isReadOnly}
                placeholder='read write'
                value={config.scope || ''}
                onChange={e => updateConfig({ scope: e.target.value })}
                helperText={
                  <>
                    <span className='block'>Space-separated list of permissions.Examples:</span>
                    <span className='block'>
                      Generic: <span className='italic'>rea d write profile</span> • GitHub:
                      <span className='italic'>repo read:user</span> • Google:
                      <span className='italic'>openid email profile</span>
                    </span>
                  </>
                }
              />

              <div>
                <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1'>Redirect URI</label>
                <div className='flex gap-2'>
                  <input
                    type='text'
                    readOnly
                    disabled={isReadOnly}
                    className='block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm sm:text-sm bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 cursor-not-allowed focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600'
                    value={redirectUri}
                  />
                  <button
                    type='button'
                    onClick={() => {
                      navigator.clipboard.writeText(redirectUri);
                    }}
                    className='inline-flex items-center px-3 py-2 border border-gray-300 dark:border-gray-600 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500'
                  >
                    <ClipboardDocumentIcon className='h-5 w-5' aria-hidden='true' />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AuthenticationConfig;

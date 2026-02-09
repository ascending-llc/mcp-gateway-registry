import type React from 'react';

import AuthenticationConfig from './AuthenticationConfig';
import type { ServerConfig } from './types';

interface MainConfigFormProps {
  formData: ServerConfig;
  isEditMode?: boolean;
  updateField: (field: keyof ServerConfig, value: any) => void;
  errors?: Record<string, string | undefined>;
  isReadOnly?: boolean;
}

const MainConfigForm: React.FC<MainConfigFormProps> = ({ formData, isEditMode, updateField, errors, isReadOnly }) => {
  const handleUpdateField = (field: keyof ServerConfig, value: any) => {
    updateField(field, value);
  };

  const handleAuthChange = (newConfig: any) => {
    updateField('authConfig', newConfig);
  };

  const getInputClass = (fieldName: string) => {
    const baseClass =
      'block w-full rounded-md shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500';
    const borderClass = errors?.[fieldName]
      ? 'border-red-500 focus:border-red-500'
      : 'border-gray-300 dark:border-gray-600';
    return `${baseClass} ${borderClass}`;
  };

  return (
    <div className='space-y-8'>
      {/* Section Basic Information */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Basic Information</h3>
        <div className='space-y-6'>
          {/* Name */}
          <div>
            <label htmlFor='serverName' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
              Server Name <span className='text-red-500'>*</span>
            </label>
            <div className='mt-1'>
              <input
                type='text'
                name='serverName'
                id='serverName'
                required
                disabled={isReadOnly}
                className={`${getInputClass('serverName')} disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder='e.g.,my-knowledge-base'
                value={formData.serverName}
                onChange={e => handleUpdateField('serverName', e.target.value)}
              />
              {errors?.serverName && <p className='mt-1 text-xs text-red-500'>{errors.serverName}</p>}
            </div>
          </div>

          {/* Description */}
          <div>
            <label htmlFor='description' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
              Description <span className='text-gray-500 dark:text-gray-400 font-normal'>(optional)</span>
            </label>
            <div className='mt-1'>
              <input
                type='text'
                name='description'
                id='description'
                disabled={isReadOnly}
                className='block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 disabled:opacity-50 disabled:cursor-not-allowed'
                placeholder='what does this server do and what tools it exposes'
                value={formData.description}
                onChange={e => handleUpdateField('description', e.target.value)}
              />
              <p className='mt-1 text-xs text-gray-500 dark:text-gray-400'>
                Be specific about capabilities (e.g., 'Exposes tools for querying PostgreSQL databases')
              </p>
            </div>
          </div>

          {/* Path */}
          <div>
            <label htmlFor='path' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
              Path <span className='text-red-500'>*</span>
            </label>
            <div className='mt-1'>
              <input
                type='text'
                name='path'
                id='path'
                required
                disabled={isReadOnly}
                className={`${getInputClass('path')} disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder='/my-server'
                value={formData.path}
                onChange={e => handleUpdateField('path', e.target.value)}
              />
              <p className='mt-1 text-xs text-gray-500 dark:text-gray-400'>
                Unique URL path prefix (must start with /)
              </p>
              {errors?.path && <p className='mt-1 text-xs text-red-500'>{errors.path}</p>}
            </div>
          </div>
        </div>
      </section>

      {/* Section Network Configuration */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Network Configuration</h3>
        <div className='space-y-6'>
          {/* MCP Server URL */}
          <div>
            <label htmlFor='url' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
              MCP Server URL <span className='text-red-500'>*</span>
            </label>
            <div className='mt-1'>
              <input
                type='url'
                name='url'
                id='url'
                required
                disabled={isReadOnly}
                className={`${getInputClass('url')} disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder='https://server.example.com:81'
                value={formData.url || ''}
                onChange={e => handleUpdateField('url', e.target.value)}
              />
              <p className='mt-1 text-xs text-gray-500 dark:text-gray-400'>
                Internal URL where your MCP server is running
              </p>
              {errors?.url && <p className='mt-1 text-xs text-red-500'>{errors.url}</p>}
            </div>
          </div>

          {/* Server Type */}
          <div>
            <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>Server Type</label>
            <div className='flex p-1 bg-gray-200 dark:bg-gray-700/50 rounded-lg'>
              <button
                type='button'
                disabled={isReadOnly}
                onClick={() => handleUpdateField('type', 'streamable-http')}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                  formData.type === 'streamable-http'
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                } ${isReadOnly ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Streamable HTTPS
              </button>
              <button
                type='button'
                disabled={isReadOnly}
                onClick={() => handleUpdateField('type', 'sse')}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
                  formData.type === 'sse'
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                } ${isReadOnly ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                SSE
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Section Authentication */}
      <AuthenticationConfig
        config={formData.authConfig}
        isEditMode={isEditMode}
        onChange={handleAuthChange}
        errors={errors}
        isReadOnly={isReadOnly}
        path={formData.path}
      />

      {/* Section Metadata */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Metadata</h3>
        <div className='space-y-6'>
          {/* Tags */}
          <div>
            <label htmlFor='tags' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
              Tags <span className='text-gray-500 dark:text-gray-400 font-normal'>(optional)</span>
            </label>
            <div className='mt-1'>
              <input
                type='text'
                name='tags'
                id='tags'
                disabled={isReadOnly}
                className={`${getInputClass('tags')} disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder='tag1,tag2,tag3'
                value={formData.tags?.join(',') || ''}
                onChange={e => {
                  const val = e.target.value;
                  const tagsArray = val ? val.split(',') : [];
                  handleUpdateField('tags', tagsArray);
                }}
              />
            </div>
          </div>

          {/* Trust Checkbox */}
          <div className='flex items-start'>
            <div className='flex h-5 items-center'>
              <input
                id='trustServer'
                name='trustServer'
                type='checkbox'
                required
                disabled={isReadOnly}
                className={`h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500 bg-white dark:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed ${
                  errors?.trustServer ? 'ring-2 ring-red-500' : ''
                }`}
                checked={formData.trustServer}
                onChange={e => {
                  handleUpdateField('trustServer', e.target.checked);
                }}
              />
            </div>
            <div className='ml-3 text-sm'>
              <label htmlFor='trustServer' className='font-medium text-gray-900 dark:text-gray-100'>
                I trust this application <span className='text-red-500'>*</span>
              </label>
              <p className='text-gray-500 dark:text-gray-400'>Custom connectors are not verified by Jarvis</p>
              {errors?.trustServer && <p className='mt-1 text-xs text-red-500'>{errors.trustServer}</p>}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default MainConfigForm;

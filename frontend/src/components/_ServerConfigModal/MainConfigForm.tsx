import { PlusIcon } from '@heroicons/react/24/outline';
import type React from 'react';

import AuthenticationConfig from './AuthenticationConfig';
import type { ServerConfig } from './types';

interface MainConfigFormProps {
  formData: ServerConfig;
  updateField: (field: keyof ServerConfig, value: any) => void;
  onClose: () => void;
  onSave: () => void;
  isEditMode: boolean;
}

const MainConfigForm: React.FC<MainConfigFormProps> = ({ formData, updateField, onClose, onSave, isEditMode }) => {
  return (
    <div className='space-y-6'>
      {/* Name */}
      <div>
        <label htmlFor='name' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
          Name <span className='text-red-500'>*</span>
        </label>
        <div className='mt-1'>
          <input
            type='text'
            name='name'
            id='name'
            required
            className='block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500'
            placeholder='Custom Tool'
            value={formData.name}
            onChange={e => updateField('name', e.target.value)}
          />
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
            className='block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500'
            placeholder='Explain what it does in a few words'
            value={formData.description}
            onChange={e => updateField('description', e.target.value)}
          />
        </div>
      </div>

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
            className='block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500'
            placeholder='https://mcp.example.com'
            value={formData.url}
            onChange={e => updateField('url', e.target.value)}
          />
        </div>
      </div>

      {/* Server Type */}
      <div>
        <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>Server Type</label>
        <div className='flex items-center space-x-6'>
          <label className='flex items-center'>
            <input
              type='radio'
              name='serverType'
              value='streamable-https'
              checked={formData.serverType === 'streamable-https'}
              onChange={() => updateField('serverType', 'streamable-https')}
              className='h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700'
            />
            <span className='ml-2 text-sm text-gray-900 dark:text-gray-100'>Streamable HTTPS</span>
          </label>
          <label className='flex items-center'>
            <input
              type='radio'
              name='serverType'
              value='sse'
              checked={formData.serverType === 'sse'}
              onChange={() => updateField('serverType', 'sse')}
              className='h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700'
            />
            <span className='ml-2 text-sm text-gray-900 dark:text-gray-100'>SSE</span>
          </label>
        </div>
      </div>

      {/* Authentication */}
      <AuthenticationConfig config={formData.authConfig} onChange={newConfig => updateField('authConfig', newConfig)} />

      {/* Trust Checkbox */}
      <div className='flex items-start'>
        <div className='flex h-5 items-center'>
          <input
            id='trustServer'
            name='trustServer'
            type='checkbox'
            required
            className='h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500 bg-white dark:bg-gray-700'
            checked={formData.trustServer}
            onChange={e => updateField('trustServer', e.target.checked)}
          />
        </div>
        <div className='ml-3 text-sm'>
          <label htmlFor='trustServer' className='font-medium text-gray-900 dark:text-gray-100'>
            I trust this application <span className='text-red-500'>*</span>
          </label>
          <p className='text-gray-500 dark:text-gray-400'>Custom connectors are not verified by Jarvis</p>
        </div>
      </div>

      {/* Footer Buttons */}
      <div className='flex justify-end space-x-3 pt-4'>
        <button
          onClick={onClose}
          className='px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500'
        >
          Cancel
        </button>
        <button
          onClick={onSave}
          className='px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-700 hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500'
        >
          {isEditMode ? 'Update' : 'Create'}
        </button>
      </div>
    </div>
  );
};

export default MainConfigForm;

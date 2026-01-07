import type React from 'react';
import { useState } from 'react';

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
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.server_name.trim()) {
      newErrors.server_name = 'Name is required';
    }

    if (!formData.path.trim()) {
      newErrors.path = 'MCP Server URL is required';
    }

    if (!formData.trustServer) {
      newErrors.trustServer = 'You must trust this application';
    }

    // Auth Validation
    const auth = formData.authConfig;
    if (auth.type === 'apiKey') {
      if (auth.source === 'global' && !auth.key?.trim()) {
        newErrors.key = 'API Key is required';
      }
    } else if (auth.type === 'oauth') {
      if (!auth.client_id?.trim()) newErrors.client_id = 'Client ID is required';
      if (!auth.client_secret?.trim()) newErrors.client_secret = 'Client Secret is required';
      if (!auth.authorization_url?.trim()) newErrors.authorization_url = 'Authorization URL is required';
      if (!auth.token_url?.trim()) newErrors.token_url = 'Token URL is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (validate()) {
      onSave();
    }
  };

  const handleUpdateField = (field: keyof ServerConfig, value: any) => {
    updateField(field, value);
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  const handleAuthChange = (newConfig: any) => {
    updateField('authConfig', newConfig);
    setErrors(prev => {
      const nextErrors = { ...prev };
      let hasChanges = false;

      if (nextErrors.key && newConfig.key?.trim()) {
        nextErrors.key = undefined;
        hasChanges = true;
      }
      if (nextErrors.client_id && newConfig.client_id?.trim()) {
        nextErrors.client_id = undefined;
        hasChanges = true;
      }
      if (nextErrors.client_secret && newConfig.client_secret?.trim()) {
        nextErrors.client_secret = undefined;
        hasChanges = true;
      }
      if (nextErrors.authorization_url && newConfig.authorization_url?.trim()) {
        nextErrors.authorization_url = undefined;
        hasChanges = true;
      }
      if (nextErrors.token_url && newConfig.token_url?.trim()) {
        nextErrors.token_url = undefined;
        hasChanges = true;
      }

      return hasChanges ? nextErrors : prev;
    });
  };

  const getInputClass = (fieldName: string) => {
    const baseClass =
      'block w-full rounded-md shadow-sm focus:border-purple-500 focus:ring-purple-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500';
    const borderClass = errors[fieldName]
      ? 'border-red-500 focus:border-red-500'
      : 'border-gray-300 dark:border-gray-600';
    return `${baseClass} ${borderClass}`;
  };

  return (
    <div className='space-y-6'>
      {/* Name */}
      <div>
        <label htmlFor='server_name' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
          Name <span className='text-red-500'>*</span>
        </label>
        <div className='mt-1'>
          <input
            type='text'
            name='server_name'
            id='server_name'
            required
            className={getInputClass('server_name')}
            placeholder='Custom Tool'
            value={formData.server_name}
            onChange={e => handleUpdateField('server_name', e.target.value)}
          />
          {errors.server_name && <p className='mt-1 text-xs text-red-500'>{errors.server_name}</p>}
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
            onChange={e => handleUpdateField('description', e.target.value)}
          />
        </div>
      </div>

      {/* MCP Server URL */}
      <div>
        <label htmlFor='path' className='block text-sm font-medium text-gray-900 dark:text-gray-100'>
          MCP Server URL <span className='text-red-500'>*</span>
        </label>
        <div className='mt-1'>
          <input
            type='url'
            name='path'
            id='path'
            required
            className={getInputClass('path')}
            placeholder='https://mcp.example.com'
            value={formData.path}
            onChange={e => handleUpdateField('path', e.target.value)}
          />
          {errors.path && <p className='mt-1 text-xs text-red-500'>{errors.path}</p>}
        </div>
      </div>

      {/* Server Type */}
      <div>
        <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>Server Type</label>
        <div className='flex items-center space-x-6'>
          <label className='flex items-center'>
            <input
              type='radio'
              name='supported_transports'
              value='streamable-https'
              checked={formData.supported_transports === 'streamable-https'}
              onChange={() => handleUpdateField('supported_transports', 'streamable-https')}
              className='h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700'
            />
            <span className='ml-2 text-sm text-gray-900 dark:text-gray-100'>Streamable HTTPS</span>
          </label>
          <label className='flex items-center'>
            <input
              type='radio'
              name='supported_transports'
              value='sse'
              checked={formData.supported_transports === 'sse'}
              onChange={() => handleUpdateField('supported_transports', 'sse')}
              className='h-4 w-4 border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-600 bg-white dark:bg-gray-700'
            />
            <span className='ml-2 text-sm text-gray-900 dark:text-gray-100'>SSE</span>
          </label>
        </div>
      </div>

      {/* Authentication */}
      <AuthenticationConfig config={formData.authConfig} onChange={handleAuthChange} errors={errors} />

      {/* Trust Checkbox */}
      <div className='flex items-start'>
        <div className='flex h-5 items-center'>
          <input
            id='trustServer'
            name='trustServer'
            type='checkbox'
            required
            className={`h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500 bg-white dark:bg-gray-700 ${errors.trustServer ? 'ring-2 ring-red-500' : ''}`}
            checked={formData.trustServer}
            onChange={e => {
              handleUpdateField('trustServer', e.target.checked);
              if (e.target.checked && errors.trustServer) {
                setErrors(prev => ({ ...prev, trustServer: undefined }));
              }
            }}
          />
        </div>
        <div className='ml-3 text-sm'>
          <label htmlFor='trustServer' className='font-medium text-gray-900 dark:text-gray-100'>
            I trust this application <span className='text-red-500'>*</span>
          </label>
          <p className='text-gray-500 dark:text-gray-400'>Custom connectors are not verified by Jarvis</p>
          {errors.trustServer && <p className='mt-1 text-xs text-red-500'>{errors.trustServer}</p>}
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
          onClick={handleSave}
          className='px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-700 hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500'
        >
          {isEditMode ? 'Update' : 'Create'}
        </button>
      </div>
    </div>
  );
};

export default MainConfigForm;

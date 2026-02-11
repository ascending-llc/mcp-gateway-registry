import type React from 'react';

import FormFields from '@/components/FormFields';
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

  return (
    <div className='space-y-8'>
      {/* Section Basic Information */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Basic Information</h3>
        <div className='space-y-6'>
          {/* Name */}
          <FormFields.InputField
            label='Server Name'
            name='serverName'
            id='serverName'
            required
            disabled={isReadOnly}
            placeholder='e.g.,my-knowledge-base'
            value={formData.serverName}
            onChange={e => handleUpdateField('serverName', e.target.value)}
            error={errors?.serverName}
          />

          {/* Description */}
          <FormFields.InputField
            label='Description (optional)'
            name='description'
            id='description'
            disabled={isReadOnly}
            placeholder='what does this server do and what tools it exposes'
            value={formData.description}
            onChange={e => handleUpdateField('description', e.target.value)}
            helperText="Be specific about capabilities (e.g., 'Exposes tools for querying PostgreSQL databases')"
          />

          {/* Path */}
          <FormFields.InputField
            label='Path'
            name='path'
            id='path'
            required
            disabled={isReadOnly}
            placeholder='/my-server'
            value={formData.path}
            onChange={e => handleUpdateField('path', e.target.value)}
            helperText='Unique URL path prefix (must start with /)'
            error={errors?.path}
          />
        </div>
      </section>

      {/* Section Network Configuration */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-2'>Network Configuration</h3>
        <div className='space-y-6'>
          {/* MCP Server URL */}
          <FormFields.InputField
            label='MCP Server URL'
            type='url'
            name='url'
            id='url'
            required
            disabled={isReadOnly}
            placeholder='https://server.example.com:81'
            value={formData.url || ''}
            onChange={e => handleUpdateField('url', e.target.value)}
            helperText='Internal URL where your MCP server is running'
            error={errors?.url}
          />

          {/* Server Type */}
          <FormFields.RadioGroupField
            label='Server Type'
            value={formData.type}
            onChange={val => handleUpdateField('type', val)}
            options={[
              { label: 'Streamable HTTPS', value: 'streamable-http' },
              { label: 'SSE', value: 'sse' },
            ]}
            disabled={isReadOnly}
          />
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
          <FormFields.InputField
            label='Tags (optional)'
            name='tags'
            id='tags'
            disabled={isReadOnly}
            placeholder='tag1,tag2,tag3'
            value={formData.tags?.join(',') || ''}
            onChange={e => {
              const val = e.target.value;
              const tagsArray = val ? val.split(',') : [];
              handleUpdateField('tags', tagsArray);
            }}
          />

          {/* Trust Checkbox */}
          <FormFields.CheckboxField
            label='I trust this application'
            name='trustServer'
            id='trustServer'
            required
            disabled={isReadOnly}
            checked={formData.trustServer}
            onChange={e => {
              handleUpdateField('trustServer', e.target.checked);
            }}
            description='Custom connectors are not verified by Jarvis'
            error={errors?.trustServer}
          />
        </div>
      </section>
    </div>
  );
};

export default MainConfigForm;

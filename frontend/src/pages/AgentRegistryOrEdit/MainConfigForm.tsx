import { useState } from 'react';
import { HiBolt, HiCheckCircle } from 'react-icons/hi2';

import FormFields from '@/components/FormFields';
import { useGlobal } from '@/contexts/GlobalContext';
import SERVICES from '@/services';
import type { Agent } from '@/services/agent/type';
import Request from '@/services/request';
import type { AgentConfig } from './types';

const TEST_URL_CANCEL_KEY = 'testAgentUrl';

interface MainConfigFormProps {
  formData: AgentConfig;
  agentDetail: Agent | null;
  updateField: (field: keyof AgentConfig, value: any) => void;
  errors?: Record<string, string | undefined>;
  isReadOnly?: boolean;
}

const MainConfigForm: React.FC<MainConfigFormProps> = ({ formData, agentDetail, updateField, errors, isReadOnly }) => {
  const { showToast } = useGlobal();
  const [testingUrl, setTestingUrl] = useState(false);
  const [urlTestPassed, setUrlTestPassed] = useState(false);
  const [discoveredData, setDiscoveredData] = useState<any>(null);

  const displayDiscoveredData = discoveredData || agentDetail?.wellKnown;

  const handleTestUrl = async () => {
    if (testingUrl) {
      const cancel = Request.cancels[TEST_URL_CANCEL_KEY];
      if (cancel) {
        cancel();
        delete Request.cancels[TEST_URL_CANCEL_KEY];
      }
      setTestingUrl(false);
      setUrlTestPassed(false);
      return;
    }

    setTestingUrl(true);
    setUrlTestPassed(false);
    setDiscoveredData(null);
    try {
      const result = await SERVICES.AGENT.testAgentUrl(formData.url, {
        cancelTokenKey: TEST_URL_CANCEL_KEY,
      } as any);
      if ((result as any)?.Code === -200) return;
      if (result?.success) {
        setUrlTestPassed(true);
        if (result.data) {
          setDiscoveredData(result.data);
        }
        showToast(result.message, 'success');
      } else {
        showToast(result.message, 'error');
      }
    } catch (error: any) {
      const errorMessage =
        typeof error?.detail === 'string'
          ? error.detail
          : typeof error?.detail?.message === 'string'
            ? error.detail.message
            : error?.message || 'Unknown error';
      showToast(errorMessage, 'error');
    } finally {
      setTestingUrl(false);
    }
  };

  const getLineCount = (jsonStr: string) => {
    return jsonStr.split('\n').length;
  };

  return (
    <div className='space-y-8'>
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-4'>Basic Information</h3>
        <div className='space-y-6'>
          {/* Title */}
          <FormFields.InputField
            label='Title'
            name='title'
            id='title'
            required
            disabled={isReadOnly}
            placeholder='e.g., My Sales Agent'
            value={formData.title}
            onChange={e => updateField('title', e.target.value)}
            error={errors?.title}
          />

          {/* Description */}
          <FormFields.InputField
            label='Description'
            name='description'
            id='description'
            disabled={isReadOnly}
            placeholder='An agent that handles CRM queries'
            value={formData.description}
            onChange={e => updateField('description', e.target.value)}
            helperText='Describe what this agent does and its capabilities.'
          />

          {/* Path */}
          <FormFields.InputField
            label='Path'
            name='path'
            id='path'
            required
            disabled={isReadOnly}
            placeholder='/my-agent'
            value={formData.path}
            onChange={e => updateField('path', e.target.value)}
            onBlur={e => updateField('path', e.target.value.toLowerCase())}
            helperText='Unique URL path prefix (must start with /)'
            error={errors?.path}
          />
        </div>
      </section>

      {/* Section Network Configuration */}
      <section>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-white mb-4'>Network Configuration</h3>
        <div className='space-y-6'>
          {/* Agent URL */}
          <FormFields.InputField
            label='Agent URL'
            type='url'
            name='url'
            id='url'
            required
            disabled={isReadOnly}
            placeholder='https://agent.example.com'
            value={formData.url || ''}
            onChange={e => {
              setUrlTestPassed(false);
              setDiscoveredData(null);
              updateField('url', e.target.value);
            }}
            helperText='The base URL where your agent is running.'
            suffix={
              <button
                type='button'
                onClick={handleTestUrl}
                disabled={isReadOnly || !formData.url}
                className='btn-input-suffix'
                title={testingUrl ? 'Cancel test' : isReadOnly ? 'Discover Disabled' : 'Test URL'}
              >
                {testingUrl ? (
                  <div className='animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 dark:border-white' />
                ) : urlTestPassed || displayDiscoveredData ? (
                  <HiCheckCircle className='h-5 w-5 text-green-500' aria-hidden='true' />
                ) : (
                  <HiBolt className='h-5 w-5' aria-hidden='true' />
                )}
              </button>
            }
            error={errors?.url}
          />
        </div>

        {/* Agent Card (Discovered payload) */}
        {displayDiscoveredData && (
          <div className='mt-8'>
            <div className='flex items-center gap-3 mb-1'>
              <h3 className='text-lg font-semibold text-gray-900 dark:text-white m-0'>Agent Card</h3>
              <span className='inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/15 text-green-300'>
                &#10003; Discovered
              </span>
              {!isReadOnly && (
                <button
                  type='button'
                  onClick={handleTestUrl}
                  disabled={testingUrl}
                  className='ml-auto text-xs text-purple-400 hover:text-purple-300 cursor-pointer disabled:opacity-50 flex items-center gap-1'
                >
                  &#8635; {testingUrl ? 'Re-discovering...' : 'Re-discover'}
                </button>
              )}
            </div>
            <div className='text-xs text-gray-400 mb-4'>
              Auto-discovered from{' '}
              <code className='px-1.5 py-0.5 bg-gray-700/50 rounded text-purple-300'>
                {formData.url ? `${formData.url.replace(/\/$/, '')}/.well-known/agent.json` : ''}
              </code>
            </div>

            <div className='border border-gray-700 rounded-lg overflow-hidden mb-8'>
              <div className='flex items-center justify-between px-3 py-2 bg-gray-800/60 border-b border-gray-700'>
                <span className='text-xs font-mono text-gray-400'>.well-known/agent.json</span>
                <span className='text-xs font-mono text-gray-400'>
                  {getLineCount(JSON.stringify(displayDiscoveredData, null, 2))} lines
                </span>
              </div>
              <pre className='bg-gray-900 text-green-300 font-mono text-xs leading-relaxed whitespace-pre overflow-x-auto p-4 m-0'>
                {JSON.stringify(displayDiscoveredData, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </section>

      <section>
        <FormFields.CheckboxField
          label='I trust this agent'
          name='trustAgent'
          id='trustAgent'
          required
          disabled={isReadOnly}
          checked={formData.trustAgent}
          onChange={e => {
            updateField('trustAgent', e.target.checked);
          }}
          description='Custom agents are not verified by Jarvis'
          error={errors?.trustAgent}
        />
      </section>
    </div>
  );
};

export default MainConfigForm;

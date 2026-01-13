import { ClipboardDocumentIcon } from '@heroicons/react/24/outline';
import type React from 'react';

interface AgentLike {
  name: string;
  path: string;
  description?: string;
  version?: string;
  visibility?: string;
  trust_level?: string;
  enabled: boolean;
  tags?: string[];
}

interface AgentDetailsModalProps {
  agent: AgentLike & { [key: string]: any };
  isOpen: boolean;
  onClose: () => void;
  loading: boolean;
  fullDetails?: any;
  onCopy?: (data: any) => Promise<void> | void;
}

const AgentDetailsModal: React.FC<AgentDetailsModalProps> = ({
  agent,
  isOpen,
  onClose,
  loading,
  fullDetails,
  onCopy,
}) => {
  if (!isOpen) {
    return null;
  }

  const dataToCopy = fullDetails || agent;

  const handleCopy = async () => {
    try {
      if (onCopy) {
        await onCopy(dataToCopy);
      } else {
        await navigator.clipboard.writeText(JSON.stringify(dataToCopy, null, 2));
      }
    } catch (error) {
      console.error('Failed to copy agent JSON:', error);
    }
  };

  return (
    <div className='fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50'>
      <div className='bg-white dark:bg-gray-800 rounded-xl p-6 max-w-4xl w-full mx-4 max-h-[80vh] overflow-auto'>
        <div className='flex items-center justify-between mb-4'>
          <h3 className='text-lg font-semibold text-gray-900 dark:text-white'>{agent.name} - Full Details (JSON)</h3>
          <button
            onClick={onClose}
            className='text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            aria-label='Close'
          >
            ✕
          </button>
        </div>

        <div className='space-y-4'>
          <div className='bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4'>
            <h4 className='font-medium text-blue-900 dark:text-blue-100 mb-2'>Complete Agent Schema</h4>
            <p className='text-sm text-blue-800 dark:text-blue-200'>
              This is the complete A2A agent definition stored in the registry. It includes all metadata, skills,
              security schemes, and configuration details.
            </p>
          </div>

          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <h4 className='font-medium text-gray-900 dark:text-white'>Agent JSON Schema:</h4>
              <button
                onClick={handleCopy}
                className='flex items-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors duration-200'
              >
                <ClipboardDocumentIcon className='h-4 w-4' />
                Copy JSON
              </button>
            </div>

            {loading ? (
              <div className='p-4 bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg text-center text-gray-600 dark:text-gray-400'>
                Loading full agent details...
              </div>
            ) : (
              <pre className='p-4 bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg overflow-x-auto text-xs text-gray-900 dark:text-gray-100 max-h-[30vh] overflow-y-auto'>
                {JSON.stringify(dataToCopy, null, 2)}
              </pre>
            )}
          </div>

          <div className='bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4'>
            <h4 className='font-medium text-gray-900 dark:text-white mb-3'>Field Reference</h4>
            <div className='grid grid-cols-1 md:grid-cols-2 gap-4 text-sm'>
              <div>
                <h5 className='font-medium text-gray-700 dark:text-gray-300 mb-2'>Core Fields</h5>
                <ul className='space-y-1 text-gray-600 dark:text-gray-400'>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>protocol_version</code> - A2A protocol
                    version
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>name</code> - Agent display name
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>description</code> - Agent purpose
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>url</code> - Agent endpoint URL
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>path</code> - Registry path
                  </li>
                </ul>
              </div>
              <div>
                <h5 className='font-medium text-gray-700 dark:text-gray-300 mb-2'>Metadata Fields</h5>
                <ul className='space-y-1 text-gray-600 dark:text-gray-400'>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>skills</code> - Agent capabilities
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>security_schemes</code> - Auth methods
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>tags</code> - Categorization
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>trust_level</code> - Verification status
                  </li>
                  <li>
                    <code className='bg-gray-200 dark:bg-gray-700 px-1 rounded'>metadata</code> - Custom data
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentDetailsModal;

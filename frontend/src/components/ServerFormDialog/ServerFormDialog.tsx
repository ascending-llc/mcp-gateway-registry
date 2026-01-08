import { Dialog } from '@headlessui/react';
import { TrashIcon, XMarkIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useEffect, useState } from 'react';

import SERVICES from '@/services';
import MainConfigForm from './MainConfigForm';
import type { AuthenticationConfig as AuthConfigType, ServerConfig } from './types';

interface ServerFormDialogProps {
  isOpen: boolean;
  showToast: (message: string, type: 'success' | 'error') => void;
  refreshData: (notLoading?: boolean) => void;
  onClose: () => void;
  id?: string | null;
}

const DEFAULT_AUTH_CONFIG: AuthConfigType = { type: 'auto', source: 'admin', auth_type: 'bearer' };

const INIT_DATA: ServerConfig = {
  server_name: '',
  description: '',
  path: '',
  url: '',
  supported_transports: 'streamable-http',
  authConfig: DEFAULT_AUTH_CONFIG,
  trustServer: false,
};

const ServerFormDialog: React.FC<ServerFormDialogProps> = ({ isOpen, showToast, refreshData, onClose, id }) => {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<ServerConfig>(INIT_DATA);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const isEditMode = !!id;

  useEffect(() => {
    if (id && isOpen) {
      getDetail();
    } else {
      setLoading(false);
      setFormData(INIT_DATA);
      setErrors({});
    }
  }, [id, isOpen]);

  const getDetail = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const result = await SERVICES.SERVER.getServerDetail(id);

      const formData: ServerConfig = {
        server_name: result.server_name,
        description: result.description,
        path: result.path,
        url: result.url || '',
        supported_transports: result.supported_transports?.[0],
        authConfig: { type: 'auto', source: 'admin', auth_type: 'bearer' },
        trustServer: true,
      };
      if (result?.apiKey) {
        formData.authConfig = {
          type: 'apiKey',
          source: result.apiKey?.source,
          auth_type: result.apiKey?.auth_type,
          key: result.apiKey?.key,
          custom_header: result.apiKey?.custom_header,
        };
      }
      if (result?.authentication) {
        formData.authConfig = {
          type: 'oauth',
          client_id: result.authentication?.client_id,
          client_secret: result.authentication?.client_secret,
          authorization_url: result.authentication?.authorization_url,
          token_url: result.authentication?.token_url,
          scope: result.authentication?.scope?.join(','),
        };
      }
      setFormData(formData);
    } catch (error) {
      console.error(error);
      showToast('Failed to fetch server details', 'error');
    } finally {
      setLoading(false);
    }
  };

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.server_name.trim()) {
      newErrors.server_name = 'Name is required';
    }

    if (!formData.path.trim()) {
      newErrors.path = 'Path is required';
    }

    if (!formData.url?.trim()) {
      newErrors.url = 'MCP Server URL is required';
    }

    if (!formData.trustServer) {
      newErrors.trustServer = 'You must trust this application';
    }

    // Auth Validation
    const auth = formData.authConfig;
    if (auth.type === 'apiKey') {
      if (auth.source === 'admin' && !auth.key?.trim()) {
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

  const updateField = (field: keyof ServerConfig, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));

    if (field === 'authConfig') {
      const newConfig = value;
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
    } else {
      if (errors[field as string]) {
        setErrors(prev => ({ ...prev, [field as string]: undefined }));
      }
    }
  };

  const processDataByAuthType = (data: ServerConfig) => {
    const baseData = {
      server_name: data.server_name,
      description: data.description,
      path: data.path,
      url: data.url,
      supported_transports: [data.supported_transports],
    };
    switch (data.authConfig.type) {
      case 'auto':
        return baseData;
      case 'apiKey':
        return {
          ...baseData,
          apiKey: {
            type: data.authConfig.type,
            source: data.authConfig.source,
            key: data.authConfig.key,
            auth_type: data.authConfig.auth_type,
            custom_header: data.authConfig.custom_header,
          },
        };
      case 'oauth':
        return {
          ...baseData,
          authentication: {
            type: data.authConfig.type,
            client_id: data.authConfig.client_id,
            client_secret: data.authConfig.client_secret,
            authorization_url: data.authConfig.authorization_url,
            token_url: data.authConfig.token_url,
            scope: data.authConfig.scope?.split(','),
          },
        };
      default:
        return {};
    }
  };

  const handleDelete = async () => {
    try {
      await SERVICES.SERVER.deleteServer(id);
      showToast('Server deleted successfully', 'success');
      onClose();
      refreshData(true);
    } catch (error: any) {
      showToast(error?.detail || error, 'error');
    }
  };

  const handleSave = async () => {
    if (!validate()) return;

    const data = processDataByAuthType(formData);
    try {
      if (isEditMode) {
        await SERVICES.SERVER.updateServer(id, data);
        showToast('Server updated successfully', 'success');
      } else {
        await SERVICES.SERVER.createServer(data);
        showToast('Server created successfully', 'success');
      }
      onClose();
      refreshData(true);
    } catch (error: any) {
      showToast(error?.detail || error, 'error');
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <Dialog as='div' className='relative z-50' open={isOpen} onClose={onClose}>
        <div className='fixed inset-0 bg-black/30' aria-hidden='true' />

        <div className='fixed inset-0 flex items-center justify-center p-4'>
          <Dialog.Panel className='w-full max-w-2xl bg-white dark:bg-gray-800 rounded-xl shadow-xl overflow-hidden max-h-[90vh] flex flex-col'>
            {/* Header */}
            <div className='px-6 py-4 flex items-center justify-between border-b border-gray-100 dark:border-gray-700'>
              <Dialog.Title className='text-lg font-bold text-gray-900 dark:text-white'>
                {isEditMode ? 'Edit MCP Server' : 'Add MCP Server'}
              </Dialog.Title>
              <button
                onClick={onClose}
                className='text-gray-400 hover:text-gray-500 dark:text-gray-400 dark:hover:text-gray-300'
              >
                <XMarkIcon className='h-6 w-6' />
              </button>
            </div>

            {/* Content */}
            <div className='px-6 py-4 overflow-y-auto custom-scrollbar flex-1'>
              {loading ? (
                <div className='flex items-center justify-center h-full min-h-[200px]'>
                  <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600'></div>
                </div>
              ) : (
                <MainConfigForm
                  formData={formData}
                  updateField={updateField}
                  onClose={onClose}
                  isEditMode={isEditMode}
                  errors={errors}
                />
              )}
            </div>

            {/* Footer */}
            <div className='px-6 py-4 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between bg-gray-50 dark:bg-gray-800/50'>
              <div>
                {isEditMode && (
                  <button
                    onClick={handleDelete}
                    className='inline-flex items-center px-4 py-2 border border-red-300 dark:border-red-800 rounded-md shadow-sm text-sm font-medium text-red-700 dark:text-red-400 bg-white dark:bg-gray-800 hover:bg-red-50 dark:hover:bg-red-900/20 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500'
                  >
                    <TrashIcon className='h-4 w-4' />
                  </button>
                )}
              </div>
              <div className='flex space-x-3'>
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
          </Dialog.Panel>
        </div>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      {/* <Dialog as='div' className='relative z-[60]' open={showDeleteConfirm} onClose={() => setShowDeleteConfirm(false)}>
        <div className='fixed inset-0 bg-black/30' aria-hidden='true' />
        <div className='fixed inset-0 flex items-center justify-center p-4'>
          <Dialog.Panel className='w-full max-w-sm bg-white dark:bg-gray-800 rounded-xl shadow-xl overflow-hidden p-6'>
            <Dialog.Title className='text-lg font-bold text-gray-900 dark:text-white mb-2'>Delete Server</Dialog.Title>
            <p className='text-sm text-gray-500 dark:text-gray-400 mb-6'>
              Are you sure you want to delete this server? This action cannot be undone.
            </p>
            <div className='flex justify-end space-x-3'>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className='px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500'
              >
                Cancel
              </button>
              <button
                onClick={() => {}}
                className='px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500'
              >
                Delete
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog> */}
    </>
  );
};

export default ServerFormDialog;

import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useEffect, useState } from 'react';

import SERVICES from '@/services';
import MainConfigForm from './MainConfigForm';
import type { AuthenticationConfig as AuthConfigType, ServerConfig } from './types';

interface ServerConfigModalProps {
  isOpen: boolean;
  showToast: (message: string, type: 'success' | 'error') => void;
  refreshData: (notLoading?: boolean) => void;
  onClose: () => void;
  id?: string | null;
}

const DEFAULT_AUTH_CONFIG: AuthConfigType = { type: 'auto', source: 'global', auth_type: 'bearer' };

const INIT_DATA: ServerConfig = {
  server_name: '',
  description: '',
  path: '',
  supported_transports: 'streamable-https',
  authConfig: DEFAULT_AUTH_CONFIG,
  trustServer: false,
};

const ServerConfigModal: React.FC<ServerConfigModalProps> = ({ isOpen, showToast, refreshData, onClose, id }) => {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<ServerConfig>(INIT_DATA);

  const isEditMode = !!id;

  useEffect(() => {
    if (id && isOpen) {
      getDetail();
    } else {
      setLoading(false);
      setFormData(INIT_DATA);
    }
  }, [id, isOpen]);

  const getDetail = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const result = await SERVICES.SERVER.getServerDetail(id);
      setFormData({
        server_name: result.server_name,
        description: result.description,
        path: result.path,
        supported_transports: result.supported_transports?.[0],
        authConfig: {
          type: result.authentication.type,
          source: result.authentication.source,
          auth_type: result.authentication.auth_type,
          key: result.authentication.key,
          custom_header: result.authentication?.custom_header,
          client_id: result.authentication?.client_id,
          client_secret: result.authentication?.client_secret,
          authorization_url: result.authentication?.authorization_url,
          token_url: result.authentication?.token_url,
          scope: result.authentication?.scope,
        },
        trustServer: true,
      });
    } catch (error) {
      console.error(error);
      showToast('Failed to fetch server details', 'error');
    } finally {
      setLoading(false);
    }
  };

  const updateField = (field: keyof ServerConfig, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const processDataByAuthType = (data: ServerConfig) => {
    const baseData = {
      server_name: data.server_name,
      description: data.description,
      path: data.path,
      supported_transports: [data.supported_transports],
      authentication: {
        type: data.authConfig.type,
      },
    };
    switch (data.authConfig.type) {
      case 'auto':
        return baseData;
      case 'apiKey':
        return {
          ...baseData,
          authentication: {
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
            scope: data.authConfig.scope,
          },
        };
      default:
        break;
    }
  };

  const handleSave = async () => {
    const data = processDataByAuthType(formData);
    try {
      if (isEditMode) {
        await SERVICES.SERVER.updateServer(id, data);
      } else {
        await SERVICES.SERVER.createServer(data);
      }
      showToast('Server created successfully', 'success');
      onClose();
      refreshData(true);
    } catch (error: any) {
      showToast(error?.detail || error, 'error');
    }
  };

  if (!isOpen) return null;

  return (
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
                onSave={handleSave}
                isEditMode={isEditMode}
              />
            )}
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
};

export default ServerConfigModal;

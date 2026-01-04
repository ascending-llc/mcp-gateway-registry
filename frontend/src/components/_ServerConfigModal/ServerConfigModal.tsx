import React, { useState, useEffect } from 'react';
import { Dialog } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';

import { ServerConfig, AuthenticationConfig as AuthConfigType } from './types';
import AuthenticationConfig from './AuthenticationConfig';
import MainConfigForm from './MainConfigForm';

interface ServerConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData?: ServerConfig; 
}

const DEFAULT_AUTH_CONFIG: AuthConfigType = {
  type: 'auto',
  apiKeySource: 'global',
  headerFormat: 'bearer',
};

const ServerConfigModal: React.FC<ServerConfigModalProps> = ({ isOpen, onClose, initialData }) => {
  const [view, setView] = useState<'main' | 'auth'>('main');
  const [formData, setFormData] = useState<ServerConfig>(initialData || {
    name: '',
    description: '',
    url: '',
    serverType: 'streamable-https',
    authConfig: DEFAULT_AUTH_CONFIG,
    trustServer: false,
  });

  const isEditMode = !!initialData;

  useEffect(() => {
    if (initialData) {
      setFormData(initialData);
    } else if (isOpen) {
      setFormData({
        name: '',
        description: '',
        url: '',
        serverType: 'streamable-https',
        authConfig: DEFAULT_AUTH_CONFIG,
        trustServer: false,
      });
    }
  }, [initialData, isOpen]);

  const updateField = (field: keyof ServerConfig, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    console.log('Saving Server Config:', formData);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
      
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="w-full max-w-2xl bg-white dark:bg-gray-800 rounded-xl shadow-xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 flex items-center justify-between border-b border-gray-100 dark:border-gray-700">
              <Dialog.Title className="text-lg font-bold text-gray-900 dark:text-white">
                {view === 'main' 
                  ? (isEditMode ? 'Edit MCP Server' : 'Add MCP Server') 
                  : 'Authentication'
                }
              </Dialog.Title>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-500 dark:text-gray-400 dark:hover:text-gray-300"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>
            
            <div className="px-6 py-6 overflow-y-auto">
               {view === 'main' ? (
                 <MainConfigForm
                   formData={formData}
                   updateField={updateField}
                   onAuthClick={() => setView('auth')}
                   onClose={onClose}
                   onSave={handleSave}
                   isEditMode={isEditMode}
                 />
               ) : (
                 <AuthenticationConfig
                   config={formData.authConfig}
                   onChange={(newConfig) => updateField('authConfig', newConfig)}
                   onCancel={() => setView('main')}
                   onSave={() => setView('main')}
                 />
               )}
            </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  );
};

export default ServerConfigModal;

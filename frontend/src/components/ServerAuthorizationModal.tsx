import { Dialog } from '@headlessui/react';
import { ArrowPathIcon, KeyIcon, TrashIcon, XMarkIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useEffect, useState } from 'react';

import SERVICE from '../services';
import { SERVER_CONNECTION } from '../services/mcp/type';

interface ServerAuthorizationModalProps {
  name: string;
  status: SERVER_CONNECTION | undefined;
  showApiKeyDialog: boolean;
  setShowApiKeyDialog: (show: boolean) => void;
  onShowToast?: (message: string, type: 'success' | 'error') => void;
  getServerStatusByPolling?: (serverNames: string) => void;
}

const ServerAuthorizationModal: React.FC<ServerAuthorizationModalProps> = ({
  name,
  status,
  showApiKeyDialog,
  setShowApiKeyDialog,
  onShowToast,
  getServerStatusByPolling,
}) => {
  const [loading, setLoading] = useState(false);
  const [authUrl, setAuthUrl] = useState('');

  const isConnecting = !!authUrl && status === SERVER_CONNECTION.CONNECTING;
  const isAuthenticated = status === SERVER_CONNECTION.CONNECTED;

  useEffect(() => {
    return () => {
      setAuthUrl('');
    };
  }, []);

  const onClickCancel = async () => {
    if (isConnecting) {
      try {
        const result = await SERVICE.MCP.cancelAuth(name);
        if (result.success) {
          setShowApiKeyDialog(false);
          return;
        }
      } catch (error) {
        onShowToast?.(error instanceof Error ? error.message : 'Unknown error', 'error');
      }
    }
    setShowApiKeyDialog(false);
  };

  const onClickAuth = async () => {
    try {
      if (authUrl) {
        window.open(authUrl, '_blank');
        getServerStatusByPolling?.(name);
        return;
      }
      setLoading(true);
      const result = await SERVICE.MCP.getServerAuthUrl(name);
      if (!result.success) {
        onShowToast?.(result.message || 'Failed to get auth URL', 'error');
        return;
      }
      setAuthUrl(result.oauthUrl);
    } catch (error) {
      onShowToast?.(error instanceof Error ? error.message : 'Unknown error', 'error');
    } finally {
    }
  };

  return (
    <Dialog
      open={showApiKeyDialog}
      onClose={setShowApiKeyDialog}
      className='fixed inset-0 z-50 flex items-center justify-center p-4'
    >
      <div className='fixed inset-0 bg-black/50' aria-hidden='true' />
      <div className='w-[512px] h-[140px] bg-white shadow-xl rounded-lg p-6 relative'>
        <div className='flex items-start justify-between mb-6'>
          <div className='flex items-center gap-4'>
            <h3 className='text-xl font-semibold text-gray-900'>{name}</h3>
            {isConnecting ? (
              <span className='flex items-center gap-1.5 text-sm text-blue-500'>
                <div className='animate-spin rounded-full h-3 w-3 border-b-2 border-slate-600' />
                Connecting
              </span>
            ) : (
              <span className='flex items-center gap-1 px-2 py-0.5 bg-amber-50 text-amber-600 rounded-full text-xs font-medium'>
                <KeyIcon className='h-3 w-3' />
                OAuth
              </span>
            )}
          </div>
          <button
            onClick={() => setShowApiKeyDialog(false)}
            className='text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
          >
            <XMarkIcon className='h-6 w-6' />
          </button>
        </div>

        <div className='flex gap-2'>
          <button
            className='px-3 h-10 border-0 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:bg-gray-500 text-sm rounded-lg cursor-pointer flex items-center justify-center gap-2'
            disabled={loading}
            onClick={onClickCancel}
          >
            {authUrl ? (
              'Cancel'
            ) : (
              <>
                <TrashIcon className='h-4 w-4' />
                Revoke
              </>
            )}
          </button>
          <button
            className={`btn-primary flex-1 h-10 text-white font-medium rounded-lg border-0 cursor-pointer flex items-center justify-center gap-2 text-sm transition-colors ${authUrl ? 'bg-green-800 hover:bg-green-700' : ''}`}
            disabled={loading}
            onClick={onClickAuth}
          >
            {loading && <div className='animate-spin rounded-full h-4 w-4 border-b-2 border-slate-200' />}
            {!(isConnecting || loading || authUrl || isAuthenticated) && <ArrowPathIcon className='h-4 w-4' />}
            {authUrl ? 'Continue with OAuth' : isAuthenticated ? 'Authenticated' : 'Authenticate'}
          </button>
        </div>
      </div>
    </Dialog>
  );
};

export default ServerAuthorizationModal;

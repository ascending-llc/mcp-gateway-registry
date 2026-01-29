import { ClipboardDocumentIcon } from '@heroicons/react/24/outline';
import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { getBasePath } from '@/config';
import type { ServerInfo } from '@/contexts/ServerContext';

type IDE = 'vscode' | 'cursor' | 'cline' | 'claude-code';

interface ServerConfigModalProps {
  server: ServerInfo;
  isOpen: boolean;
  onClose: () => void;
  onShowToast?: (message: string, type: 'success' | 'error') => void;
}

const ServerConfigModal: React.FC<ServerConfigModalProps> = ({ server, isOpen, onClose, onShowToast }) => {
  const [selectedIDE, setSelectedIDE] = useState<IDE>('vscode');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      console.log('aaaa');
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const generateMCPConfig = useCallback(() => {
    const serverName = server.name
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '');

    // Get base URL and strip port for nginx proxy compatibility
    const currentUrl = new URL(window.location.origin);
    const basePath = getBasePath();
    const url = `${currentUrl.protocol}//${currentUrl.hostname}${basePath}/proxy${server.path}`;

    switch (selectedIDE) {
      case 'vscode':
        return {
          servers: {
            [serverName]: {
              type: 'http',
              url,
              headers: {
                Authorization: 'Bearer [YOUR_AUTH_TOKEN]',
              },
            },
          },
          inputs: [
            {
              type: 'promptString',
              id: 'auth-token',
              description: 'Gateway Authentication Token',
            },
          ],
        };
      case 'cursor':
        return {
          mcpServers: {
            [serverName]: {
              url,
              headers: {
                Authorization: 'Bearer [YOUR_AUTH_TOKEN]',
              },
            },
          },
        };
      case 'cline':
        return {
          mcpServers: {
            [serverName]: {
              type: 'streamableHttp',
              url,
              disabled: false,
              headers: {
                Authorization: 'Bearer [YOUR_AUTH_TOKEN]',
              },
            },
          },
        };
      case 'claude-code':
        return {
          mcpServers: {
            [serverName]: {
              type: 'http',
              url,
              headers: {
                Authorization: 'Bearer [YOUR_AUTH_TOKEN]',
              },
            },
          },
        };
      default:
        return {
          mcpServers: {
            [serverName]: {
              type: 'http',
              url,
              headers: {
                Authorization: 'Bearer [YOUR_AUTH_TOKEN]',
              },
            },
          },
        };
    }
  }, [server.name, server.path, selectedIDE]);

  const copyConfigToClipboard = useCallback(async () => {
    try {
      const config = generateMCPConfig();
      const configText = JSON.stringify(config, null, 2);
      await navigator.clipboard.writeText(configText);

      onShowToast?.('Configuration copied to clipboard!', 'success');
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      onShowToast?.('Failed to copy configuration', 'error');
    }
  }, [generateMCPConfig, onShowToast]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className='fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50'>
      <div className='bg-white dark:bg-gray-800 rounded-xl p-6 max-w-3xl w-full mx-4 max-h-[80vh]'>
        <div className='flex items-center justify-between mb-4'>
          <h3 className='text-lg font-semibold text-gray-900 dark:text-white'>MCP Configuration for {server.name}</h3>
          <button
            onClick={onClose}
            className='text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
          >
            ✕
          </button>
        </div>

        <div className='space-y-4 overflow-auto max-h-[calc(80vh-100px)]'>
          <div className='bg-gray-50 dark:bg-gray-900 border dark:border-gray-700 rounded-lg p-4'>
            <h4 className='font-medium text-gray-900 dark:text-white mb-3'>Select your IDE/Tool:</h4>
            <div className='flex flex-wrap gap-2'>
              {(['vscode', 'cursor', 'cline', 'claude-code'] as IDE[]).map(ide => (
                <button
                  key={ide}
                  onClick={() => setSelectedIDE(ide)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    selectedIDE === ide
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                  }`}
                >
                  {ide === 'vscode'
                    ? 'VS Code'
                    : ide === 'cursor'
                      ? 'Cursor'
                      : ide === 'cline'
                        ? 'Cline'
                        : 'Claude Code'}
                </button>
              ))}
            </div>
            <p className='text-xs text-gray-600 dark:text-gray-400 mt-2'>
              Configuration format optimized for{' '}
              {selectedIDE === 'vscode'
                ? 'VS Code'
                : selectedIDE === 'cursor'
                  ? 'Cursor'
                  : selectedIDE === 'cline'
                    ? 'Cline'
                    : 'Claude Code'}{' '}
              integration
            </p>
          </div>

          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <h4 className='font-medium text-gray-900 dark:text-white'>Configuration JSON:</h4>
              <button
                onClick={copyConfigToClipboard}
                className='flex items-center gap-2 px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors duration-200'
              >
                <ClipboardDocumentIcon className='h-4 w-4' />
                Copy to Clipboard
              </button>
            </div>
            <pre className='bg-gray-900 text-green-100 p-4 rounded-lg text-sm overflow-x-auto'>
              {JSON.stringify(generateMCPConfig(), null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ServerConfigModal;

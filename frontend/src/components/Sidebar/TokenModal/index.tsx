import { Dialog, Transition } from '@headlessui/react';
import { ArrowDownTrayIcon, CheckIcon, ClipboardIcon } from '@heroicons/react/24/outline';
import { Fragment, useState } from 'react';

type TokenModalProps = {
  tokenData: any;
  showTokenModal: boolean;
  setShowTokenModal: (show: boolean) => void;
};

const TokenModal: React.FC<TokenModalProps> = ({ tokenData, showTokenModal, setShowTokenModal }) => {
  const [copied, setCopied] = useState(false);

  /** Handle copying token data to clipboard */
  const handleCopyTokens = async () => {
    if (!tokenData) return;

    const formattedData = JSON.stringify(tokenData, null, 2);
    try {
      await navigator.clipboard.writeText(formattedData);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  /** Handle downloading token data as a JSON file */
  const handleDownloadTokens = () => {
    if (!tokenData) return;

    const formattedData = JSON.stringify(tokenData, null, 2);
    const blob = new Blob([formattedData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mcp-registry-api-tokens-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Transition appear show={showTokenModal} as={Fragment}>
      <Dialog as='div' className='relative z-50' onClose={() => setShowTokenModal(false)}>
        <Transition.Child
          as={Fragment}
          enter='ease-out duration-300'
          enterFrom='opacity-0'
          enterTo='opacity-100'
          leave='ease-in duration-200'
          leaveFrom='opacity-100'
          leaveTo='opacity-0'
        >
          <div className='fixed inset-0 bg-black bg-opacity-25' />
        </Transition.Child>

        <div className='fixed inset-0 overflow-y-auto'>
          <div className='flex min-h-full items-center justify-center p-4 text-center'>
            <Transition.Child
              as={Fragment}
              enter='ease-out duration-300'
              enterFrom='opacity-0 scale-95'
              enterTo='opacity-100 scale-100'
              leave='ease-in duration-200'
              leaveFrom='opacity-100 scale-100'
              leaveTo='opacity-0 scale-95'
            >
              <Dialog.Panel className='w-full max-w-3xl transform overflow-hidden rounded-2xl bg-white dark:bg-gray-800 p-6 text-left align-middle shadow-xl transition-all'>
                <Dialog.Title as='h3' className='text-lg font-medium leading-6 text-gray-900 dark:text-white mb-4'>
                  Keycloak Admin Tokens
                </Dialog.Title>

                {tokenData && (
                  <div className='space-y-4'>
                    {/* Action Buttons */}
                    <div className='flex space-x-2'>
                      <button
                        onClick={handleCopyTokens}
                        className='flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm'
                      >
                        {copied ? (
                          <>
                            <CheckIcon className='h-4 w-4' />
                            <span>Copied!</span>
                          </>
                        ) : (
                          <>
                            <ClipboardIcon className='h-4 w-4' />
                            <span>Copy JSON</span>
                          </>
                        )}
                      </button>
                      <button
                        onClick={handleDownloadTokens}
                        className='flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm'
                      >
                        <ArrowDownTrayIcon className='h-4 w-4' />
                        <span>Download JSON</span>
                      </button>
                    </div>

                    {/* Token Data Display */}
                    <div className='bg-gray-50 dark:bg-gray-900 rounded-lg p-4 max-h-96 overflow-y-auto'>
                      <pre className='text-xs text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-all'>
                        {JSON.stringify(tokenData, null, 2)}
                      </pre>
                    </div>

                    {/* Close Button */}
                    <div className='flex justify-end'>
                      <button
                        onClick={() => setShowTokenModal(false)}
                        className='px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm'
                      >
                        Close
                      </button>
                    </div>
                  </div>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

export default TokenModal;

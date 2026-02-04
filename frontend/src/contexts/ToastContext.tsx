import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { CheckCircleIcon, ExclamationCircleIcon, XMarkIcon } from '@heroicons/react/24/outline';

interface ToastContextType {
  showToast: (message: string, type: 'success' | 'error') => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

interface ToastProviderProps {
  children: React.ReactNode;
}

interface Toast {
  message: string;
  type: 'success' | 'error';
  id: number;
}

// Toast notification component
interface ToastItemProps {
  message: string;
  type: 'success' | 'error';
  onClose: () => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ message, type, onClose }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, 4000);

    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border ${
        type === 'success'
          ? 'bg-green-50 dark:bg-green-900/90 border-green-200 dark:border-green-700'
          : 'bg-red-50 dark:bg-red-900/90 border-red-200 dark:border-red-700'
      } animate-in slide-in-from-top-2 duration-300`}
    >
      {type === 'success' ? (
        <CheckCircleIcon className='h-5 w-5 text-green-600 dark:text-green-400 flex-shrink-0' />
      ) : (
        <ExclamationCircleIcon className='h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0' />
      )}
      <p
        className={`text-sm font-medium flex-1 ${
          type === 'success'
            ? 'text-green-800 dark:text-green-200'
            : 'text-red-800 dark:text-red-200'
        }`}
      >
        {message}
      </p>
      <button
        onClick={onClose}
        className={`p-1 rounded-md transition-colors ${
          type === 'success'
            ? 'hover:bg-green-100 dark:hover:bg-green-800'
            : 'hover:bg-red-100 dark:hover:bg-red-800'
        }`}
      >
        <XMarkIcon
          className={`h-4 w-4 ${
            type === 'success'
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}
        />
      </button>
    </div>
  );
};

export const ToastProvider: React.FC<ToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [nextId, setNextId] = useState(0);

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = Date.now();
    setToasts(prev => [...prev, { message: String(message), type, id }]);
    setNextId(prev => prev + 1);
  }, []);

  const hideToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div className='fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md'>
          {toasts.map(toast => (
            <ToastItem
              key={toast.id}
              message={toast.message}
              type={toast.type}
              onClose={() => hideToast(toast.id)}
            />
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextType => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};

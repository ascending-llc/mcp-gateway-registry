import type React from 'react';
import type { BaseFieldProps } from './types';

/**
 * CheckboxField Props
 */
export interface CheckboxFieldProps extends BaseFieldProps, Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  description?: React.ReactNode;
}

/**
 * Reusable Checkbox Field Component
 */
export const CheckboxField: React.FC<CheckboxFieldProps> = ({
  label,
  description,
  className = '',
  error,
  required,
  disabled,
  id,
  ...props
}) => {
  const generatedId = id || props.name;

  return (
    <div className={`flex items-start ${className}`}>
      <div className='flex h-5 items-center'>
        <input
          id={generatedId}
          type='checkbox'
          disabled={disabled}
          required={required}
          className={`h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-purple-600 focus:ring-purple-500 bg-white dark:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed ${
            error ? 'ring-2 ring-red-500' : ''
          }`}
          {...props}
        />
      </div>
      <div className='ml-3 text-sm'>
        {label && (
          <label htmlFor={generatedId} className='font-medium text-gray-900 dark:text-gray-100'>
            {label} {required && <span className='text-red-500'>*</span>}
          </label>
        )}
        {description && <div className='text-gray-500 dark:text-gray-400'>{description}</div>}
        {error && <p className='mt-1 text-xs text-red-500'>{error}</p>}
      </div>
    </div>
  );
};

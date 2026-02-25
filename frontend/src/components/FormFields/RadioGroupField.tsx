import type React from 'react';
import type { RadioOption } from './types';

interface RadioGroupFieldProps {
  label?: string;
  options: RadioOption[];
  value: string | number;
  onChange: (value: any) => void;
  className?: string;
  disabled?: boolean;
  name?: string;
}

/**
 * Reusable Radio Group Field Component (Segmented Control style)
 */
export const RadioGroupField: React.FC<RadioGroupFieldProps> = ({
  label,
  options,
  value,
  onChange,
  className = '',
  disabled,
}) => {
  return (
    <div className={className}>
      {label && <label className='block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2'>{label}</label>}
      <div className='flex p-1 bg-gray-200 dark:bg-gray-700/50 rounded-lg'>
        {options.map(option => (
          <button
            key={option.value}
            type='button'
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-all duration-200 ${
              value === option.value
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
};

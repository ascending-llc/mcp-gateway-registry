import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { EyeIcon, EyeSlashIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

interface OAuthProvider {
  name: string;
  display_name: string;
  icon?: string;
}

const Login: React.FC = () => {
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{username?: string, password?: string}>({});
  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([]);
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockOn, setCapsLockOn] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [authServerUrl, setAuthServerUrl] = useState<string>('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    console.log('[Login] Component mounted, fetching OAuth providers...');
    fetchAuthConfig();
    fetchOAuthProviders();

    // Check for error parameter from URL (e.g., from OAuth callback)
    const urlError = searchParams.get('error');
    if (urlError) {
      setError(decodeURIComponent(urlError));
    }

    // Check if user preferences exist
    const savedRememberMe = localStorage.getItem('rememberMe') === 'true';
    const savedUsername = localStorage.getItem('savedUsername');
    setRememberMe(savedRememberMe);
    if (savedRememberMe && savedUsername) {
      setCredentials(prev => ({ ...prev, username: savedUsername }));
    }
  }, [searchParams]);

    const fetchAuthConfig = async () => {
        try {
            const response = await axios.get('/api/auth/config');
            setAuthServerUrl(response.data.auth_server_url || '');
        } catch (error) {
            console.error('Failed to fetch auth config:', error);
            // Fallback to localhost for development
            setAuthServerUrl('http://localhost:8888');
        }
    };

  // Log when oauthProviders state changes
  useEffect(() => {
    console.log('[Login] oauthProviders state changed:', oauthProviders);
  }, [oauthProviders]);

  const fetchOAuthProviders = async () => {
    try {
      console.log('[Login] Fetching OAuth providers from /api/auth/providers');
      // Call the registry auth providers endpoint
      const response = await axios.get('/api/auth/providers');
      console.log('[Login] Response received:', response.data);
      console.log('[Login] Providers:', response.data.providers);
      setOauthProviders(response.data.providers || []);
      console.log('[Login] State updated with', response.data.providers?.length || 0, 'providers');
    } catch (error) {
      console.error('[Login] Failed to fetch OAuth providers:', error);
      // Don't show error for missing OAuth providers, just continue with basic auth
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    setCapsLockOn(e.getModifierState('CapsLock'));
  };

  const validateField = (field: string, value: string) => {
    const errors: {username?: string, password?: string} = {};
    
    if (field === 'username' && value.trim().length === 0) {
      errors.username = 'Username is required';
    } else if (field === 'username' && value.length < 2) {
      errors.username = 'Username must be at least 2 characters';
    }
    
    if (field === 'password' && value.length === 0) {
      errors.password = 'Password is required';
    } else if (field === 'password' && value.length < 3) {
      errors.password = 'Password must be at least 3 characters';
    }
    
    setFieldErrors(prev => ({ ...prev, ...errors }));
    return Object.keys(errors).length === 0;
  };

  const handleInputChange = (field: string, value: string) => {
    setCredentials(prev => ({ ...prev, [field]: value }));
    // Clear field-specific errors when user starts typing
    if (fieldErrors[field as keyof typeof fieldErrors]) {
      setFieldErrors(prev => ({ ...prev, [field]: undefined }));
    }
    // Clear general error
    if (error) {
      setError('');
    }
  };

  const handleInputBlur = (field: string, value: string) => {
    validateField(field, value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setFieldErrors({});
    
    // Validate all fields
    const usernameValid = validateField('username', credentials.username);
    const passwordValid = validateField('password', credentials.password);
    
    if (!usernameValid || !passwordValid) {
      setLoading(false);
      return;
    }
    
    try {
      await login(credentials.username, credentials.password);
      
      // Handle remember me
      if (rememberMe) {
        localStorage.setItem('rememberMe', 'true');
        localStorage.setItem('savedUsername', credentials.username);
      } else {
        localStorage.removeItem('rememberMe');
        localStorage.removeItem('savedUsername');
      }
      
      navigate('/');
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Login failed';
      
      // Provide more specific error messages
      if (errorMessage.toLowerCase().includes('credential') || errorMessage.toLowerCase().includes('password')) {
        setError('Invalid username or password. Please check your credentials and try again.');
      } else if (errorMessage.toLowerCase().includes('user') && errorMessage.toLowerCase().includes('not found')) {
        setError('User not found. Please check your username or contact support.');
      } else if (errorMessage.toLowerCase().includes('disabled') || errorMessage.toLowerCase().includes('blocked')) {
        setError('Account is disabled. Please contact support for assistance.');
      } else {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = (provider: string) => {
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const currentOrigin = window.location.origin;
    const redirectUri = encodeURIComponent(currentOrigin + '/');

    // Use the auth server URL from config, fallback to localhost if not loaded yet
    const authUrl = authServerUrl || 'http://localhost:8888';
    window.location.href = `${authUrl}/oauth2/login/${provider}?redirect_uri=${redirectUri}`;
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h2 className="text-center text-3xl font-bold text-gray-900 dark:text-white">
          Sign in to MCP Servers & A2A Agents Registry
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
          Access your MCP server management dashboard
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="card p-8">
          {/* OAuth Providers */}
          {oauthProviders.length > 0 && (
            <div className="space-y-3 mb-6">
              {oauthProviders.map((provider) => (
                <button
                  key={provider.name}
                  onClick={() => handleOAuthLogin(provider.name)}
                  className="w-full flex items-center justify-center px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg shadow-sm text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 transition-all duration-200 hover:shadow-md"
                >
                  <span>Continue with {provider.display_name}</span>
                </button>
              ))}

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300 dark:border-gray-600" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-4 bg-gray-50 dark:bg-gray-900 text-gray-500 dark:text-gray-400">
                    Or continue with username
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Traditional Login Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="p-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg dark:bg-red-900/30 dark:text-red-400 dark:border-red-800 flex items-start space-x-2">
                <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Username
              </label>
              <input
                id="username"
                type="text"
                required
                autoComplete="username"
                className={`input mt-1 ${fieldErrors.username ? 'border-red-300 dark:border-red-600 focus:ring-red-500 focus:border-red-500' : ''}`}
                value={credentials.username}
                onChange={(e) => handleInputChange('username', e.target.value)}
                onBlur={(e) => handleInputBlur('username', e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder="Enter your username"
              />
              {fieldErrors.username && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">{fieldErrors.username}</p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
                  className={`input mt-1 pr-12 ${fieldErrors.password ? 'border-red-300 dark:border-red-600 focus:ring-red-500 focus:border-red-500' : ''}`}
                  value={credentials.password}
                  onChange={(e) => handleInputChange('password', e.target.value)}
                  onBlur={(e) => handleInputBlur('password', e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeSlashIcon className="h-5 w-5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
                  ) : (
                    <EyeIcon className="h-5 w-5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
                  )}
                </button>
              </div>
              {fieldErrors.password && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-400">{fieldErrors.password}</p>
              )}
              {capsLockOn && (
                <p className="mt-1 text-sm text-yellow-600 dark:text-yellow-400 flex items-center space-x-1">
                  <ExclamationTriangleIcon className="h-4 w-4" />
                  <span>Caps Lock is on</span>
                </p>
              )}
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <input
                  id="remember-me"
                  name="remember-me"
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-700"
                />
                <label htmlFor="remember-me" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                  Remember me
                </label>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center space-x-2"
            >
              {loading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Signing in...</span>
                </>
              ) : (
                <span>Sign in</span>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Login; 
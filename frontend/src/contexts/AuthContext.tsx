import axios from 'axios';
import type React from 'react';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

import { getBasePath } from '@/config';
import SERVICES from '@/services';

// Configure axios to include credentials (cookies) with all requests
axios.defaults.withCredentials = true;

// Add base URL from runtime config
axios.defaults.baseURL = getBasePath() || '/';

interface User {
  username: string;
  email?: string;
  scopes?: string[];
  groups?: string[];
  auth_method?: string;
  provider?: string;
  can_modify_servers?: boolean;
  is_admin?: boolean;
}

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const userData = await SERVICES.AUTH.getAuthMe();
      setUser({
        username: userData.username,
        email: userData.email,
        scopes: userData.scopes || [],
        groups: userData.groups || [],
        auth_method: userData.auth_method || 'basic',
        provider: userData.provider,
        can_modify_servers: userData.can_modify_servers || false,
        is_admin: userData.is_admin || false,
      });
    } catch (_error) {
      // User not authenticated
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (username: string, password: string) => {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    const response = await axios.post('/api/auth/login', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    if (response.status === 200) {
      await checkAuth();
    }
  };

  const logout = async () => {
    try {
      await axios.post('/logout');
    } catch (_error) {
      // Ignore errors during logout
    } finally {
      setUser(null);
    }
  };

  const value = {
    user,
    login,
    logout,
    loading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

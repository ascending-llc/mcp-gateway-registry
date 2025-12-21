import React, { useState, useEffect, Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { Link } from 'react-router-dom';
import { 
  Bars3Icon, 
  UserIcon, 
  ChevronDownIcon,
  ArrowRightOnRectangleIcon,
  KeyIcon,
  Cog6ToothIcon,
  SunIcon,
  MoonIcon
} from '@heroicons/react/24/outline';
import Sidebar from './Sidebar';
import { useServerStats } from '../hooks/useServerStats';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import logo from '../assets/logo.png';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [version, setVersion] = useState<string | null>(null);
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { stats, activeFilter, setActiveFilter } = useServerStats();

  useEffect(() => {
    // Fetch version from API
    fetch('/api/version')
      .then(res => res.json())
      .then(data => setVersion(data.version))
      .catch(err => console.error('Failed to fetch version:', err));
  }, []);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
        <div className="px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Left side */}
            <div className="flex items-center">
              {/* Sidebar toggle button - visible on all screen sizes */}
              <button
                type="button"
                className="p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-purple-500 mr-2"
                onClick={() => {
                  console.log('Toggle clicked, current state:', sidebarOpen);
                  setSidebarOpen(!sidebarOpen);
                }}
              >
                <Bars3Icon className="h-6 w-6" />
              </button>

              {/* Logo */}
              <div className="flex items-center ml-2 md:ml-0">
                <Link to="/" className="flex items-center hover:opacity-80 transition-opacity">
                  <img
                    src={logo}
                    alt="MCP Servers & A2A Agents Registry Logo"
                    className="h-8 w-8 dark:brightness-0 dark:invert"
                  />
                  <span className="ml-2 text-xl font-bold text-gray-900 dark:text-white">
                    MCP Servers & A2A Agents Registry
                  </span>
                </Link>
              </div>
            </div>

            {/* Right side */}
            <div className="flex items-center space-x-4">
              {/* GitHub link */}
              <a
                href="https://github.com/agentic-community/mcp-gateway-registry"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-gray-400 hover:text-gray-500 dark:text-gray-300 dark:hover:text-gray-100 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                title="View on GitHub"
              >
                <svg
                  className="h-5 w-5"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0110 4.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.203 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.942.359.31.678.921.678 1.856 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0020 10.017C20 4.484 15.522 0 10 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </a>

              {/* Version badge */}
              {version && (
                <div className="hidden md:flex items-center px-2.5 py-1 bg-purple-50 dark:bg-purple-900/20 rounded-md">
                  <span className="text-xs font-medium text-purple-700 dark:text-purple-300">
                    {version}
                  </span>
                </div>
              )}

              {/* Theme toggle */}
              <button
                onClick={toggleTheme}
                className="p-2 text-gray-400 hover:text-gray-500 dark:text-gray-300 dark:hover:text-gray-100 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                {theme === 'dark' ? (
                  <SunIcon className="h-5 w-5" />
                ) : (
                  <MoonIcon className="h-5 w-5" />
                )}
              </button>

              {/* User dropdown */}
              <Menu as="div" className="relative">
                <div>
                  <Menu.Button className="flex items-center space-x-3 text-sm rounded-full focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 p-2 hover:bg-gray-100 dark:hover:bg-gray-700">
                    <div className="h-8 w-8 rounded-full bg-purple-100 dark:bg-purple-800 flex items-center justify-center">
                      <UserIcon className="h-5 w-5 text-purple-600 dark:text-purple-300" />
                    </div>
                    <span className="hidden md:block text-gray-700 dark:text-gray-100 font-medium">
                      {user?.username || 'Admin'}
                    </span>
                    <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                  </Menu.Button>
                </div>

                <Transition
                  as={Fragment}
                  enter="transition ease-out duration-100"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-75"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Menu.Items className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-md bg-white dark:bg-gray-800 py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings"
                          className={`${
                            active ? 'bg-gray-100 dark:bg-gray-800' : ''
                          } flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-100`}
                        >
                          <Cog6ToothIcon className="mr-3 h-4 w-4" />
                          Settings
                        </Link>
                      )}
                    </Menu.Item>

                    <div className="border-t border-gray-100 dark:border-gray-700 my-1" />
                    
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          onClick={handleLogout}
                          className={`${
                            active ? 'bg-gray-100 dark:bg-gray-800' : ''
                          } flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-100`}
                        >
                          <ArrowRightOnRectangleIcon className="mr-3 h-4 w-4" />
                          Sign out
                        </button>
                      )}
                    </Menu.Item>
                  </Menu.Items>
                </Transition>
              </Menu>
            </div>
          </div>
        </div>
      </header>

      <div className="flex h-screen pt-16">
        {/* Sidebar */}
        <Sidebar 
          sidebarOpen={sidebarOpen} 
          setSidebarOpen={setSidebarOpen}
          stats={stats}
          activeFilter={activeFilter}
          setActiveFilter={setActiveFilter}
        />


        {/* Main content */}
        <main className={`flex-1 flex flex-col transition-all duration-300 ${
          sidebarOpen ? 'md:ml-64 lg:ml-72 xl:ml-80' : ''
        }`}>
          <div className="flex-1 flex flex-col px-4 sm:px-6 lg:px-8 py-4 md:py-8 overflow-hidden">
            {React.cloneElement(children as React.ReactElement, { activeFilter })}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout; 
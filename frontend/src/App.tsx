import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ServerProvider } from './contexts/ServerContext';
import { getBasePath } from './config';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import TokenGeneration from './pages/TokenGeneration';
import Login from './pages/Login';
import OAuthCallback from './pages/OAuthCallback';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ServerProvider>
          <Router basename={getBasePath() || '/'}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/auth/callback" element={<OAuthCallback />} />
              <Route path="/" element={
                <ProtectedRoute>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              } />
              <Route path="/generate-token" element={
                <ProtectedRoute>
                  <Layout>
                    <TokenGeneration />
                  </Layout>
                </ProtectedRoute>
              } />
            </Routes>
          </Router>
        </ServerProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App; 
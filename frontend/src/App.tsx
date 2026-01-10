import { Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { getBasePath } from './config';
import { AuthProvider } from './contexts/AuthContext';
import { ServerProvider } from './contexts/ServerContext';
import { ThemeProvider } from './contexts/ThemeContext';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import OAuthCallback from './pages/OAuthCallback';
import TokenGeneration from './pages/TokenGeneration';

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ServerProvider>
          <Router basename={getBasePath() || '/'}>
            <Routes>
              <Route path='/login' element={<Login />} />
              <Route path='/oauth/callback' element={<OAuthCallback />} />
              <Route
                path='/'
                element={
                  <ProtectedRoute>
                    <Layout>
                      <Dashboard />
                    </Layout>
                  </ProtectedRoute>
                }
              />
              <Route
                path='/generate-token'
                element={
                  <ProtectedRoute>
                    <Layout>
                      <TokenGeneration />
                    </Layout>
                  </ProtectedRoute>
                }
              />
            </Routes>
          </Router>
        </ServerProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;

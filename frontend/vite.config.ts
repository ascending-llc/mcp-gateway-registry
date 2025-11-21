import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendPort = process.env.REGISTRY_PORT && Number(process.env.REGISTRY_PORT) || 7860;
const backendURL = process.env.REGISTRY_URL ? `http://${process.env.REGISTRY_URL}:${backendPort}` : `http://localhost:${backendPort}`;
const authURL = process.env.AUTH_SERVER_EXTERNAL_URL ? process.env.AUTH_SERVER_URL : `http://localhost:8888`;

export default defineConfig({
  plugins: [react()],
  base: '/gateway/', // Add this line for production builds
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/v0': {
        target: backendURL,
        changeOrigin: true,
      },
      '/api/auth/providers': {
        target: authURL, 
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/auth\/providers/, '/oauth2/providers'),
      },
      '/api': {
        target: backendURL, 
        changeOrigin: true,
      },
      '/health': {
        target: backendURL, 
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
});
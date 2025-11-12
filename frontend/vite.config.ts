import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendPort = process.env.REGISTRY_PORT && Number(process.env.REGISTRY_PORT) || 7860;
const backendURL = process.env.REGISTRY_URL ? `http://${process.env.REGISTRY_URL}:${backendPort}` : `http://localhost:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/v0': {
        target: backendURL,
        changeOrigin: true,
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
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/v0': {
        target: 'http://localhost:7860', // TODO: Update to registry-backend URL
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:7860', // TODO: Update to registry-backend URL
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:7860', // TODO: Update to registry-backend URL
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
});
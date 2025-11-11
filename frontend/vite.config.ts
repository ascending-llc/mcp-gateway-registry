import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/v0': {
        target: 'http://localhost:7860', // running outside of docker container; DNS resolution via container name won't work
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:7860', // running outside of docker container; DNS resolution via container name won't work
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:7860', // running outside of docker container; DNS resolution via container name won't work
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
});
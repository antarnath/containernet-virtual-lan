import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite config — proxies /api calls to the backend during development.
// In production the frontend is served by Nginx; the proxy is not used.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
});

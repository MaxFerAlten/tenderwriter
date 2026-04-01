import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8000';
const mattermostTarget = process.env.VITE_MM_TARGET || 'http://localhost:8065';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    watch: {
      usePolling: true,
      interval: 500,
    },
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '/mm': {
        target: mattermostTarget,
        changeOrigin: true,
        ws: true,
        xfwd: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined;
          }
          if (id.includes('framer-motion')) {
            return 'motion';
          }

          if (id.includes('lucide-react')) {
            return 'icons';
          }

          if (id.includes('react') || id.includes('scheduler')) {
            return 'react-vendor';
          }

          return 'vendor';
        },
      },
    },
  },
});

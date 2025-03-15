import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react({
      fastRefresh: true,
      jsxRuntime: 'classic',
    }),
  ],
  base: '/',
  build: {
    outDir: '../backend/static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    host: true,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      react: require.resolve('react'),
      'react-dom': require.resolve('react-dom'),
    },
  },
});
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['.lan', '.local', '192.168.50.106'],
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://python-hub:8766',
        changeOrigin: true,
      },
    },
  },
})
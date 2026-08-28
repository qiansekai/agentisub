import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8720',
      '/media': 'http://127.0.0.1:8720',
    },
  },
  build: { outDir: 'dist' },
})

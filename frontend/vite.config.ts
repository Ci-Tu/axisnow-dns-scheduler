import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 开发时把 /api 代理到本地后端（默认 4894 端口）
const backend = process.env.VITE_BACKEND ?? 'http://127.0.0.1:4894'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1200,
  },
})

import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: process.env.VITE_BASE || '/static/dist/',
  publicDir: false,
  plugins: [tailwindcss()],
  build: {
    outDir: process.env.VITE_OUTPUT_DIR || 'static/dist',
    manifest: true,
    emptyOutDir: true,
    rollupOptions: { input: ['frontend/site.js', 'frontend/shop.js'] },
  },
  server: { watch: { ignored: ['**/.venv/**', '**/var/**', '**/artifacts/**'] } },
})

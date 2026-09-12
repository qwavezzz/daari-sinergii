import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  base: process.env.VITE_BASE || '/static/dist/',
  publicDir: false,
  resolve: {
    alias: {
      '#navigation-transport':
        process.env.VITE_STATIC_DEMO === 'true'
          ? fileURLToPath(new URL('./frontend/navigation-demo.js', import.meta.url))
          : 'htmx.org',
    },
  },
  plugins: [tailwindcss()],
  build: {
    outDir: process.env.VITE_OUTPUT_DIR || 'static/dist',
    manifest: true,
    emptyOutDir: true,
    rollupOptions: { input: ['frontend/site.js', 'frontend/shop.js'] },
  },
  server: { watch: { ignored: ['**/.venv/**', '**/var/**', '**/artifacts/**'] } },
})

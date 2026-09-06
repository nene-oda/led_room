import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Origen del backend durante el desarrollo.
 *
 * En produccion el SPA lo sirve FastAPI desde el mismo origen, asi que el
 * cliente usa rutas relativas y este proxy no interviene.
 */
const BACKEND_ORIGIN = 'http://localhost:8000'

export default defineConfig({
  // El SPA se sirve desde la raiz del origen (FastAPI monta /assets y el
  // catch-all). Con './' las rutas relativas romperian el fallback del SPA en
  // rutas profundas como /scenes/night.
  base: '/',

  plugins: [react()],

  server: {
    // Expone el dev server en la LAN para probar desde el movil.
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: BACKEND_ORIGIN, changeOrigin: true },
      // ws: true es obligatorio para que el upgrade de WebSocket funcione.
      // La ruta aun no existe en el backend (Fase 4), pero dejarla configurada
      // evita tocar esta config cuando llegue.
      '/ws': { target: BACKEND_ORIGIN, ws: true, changeOrigin: true },
    },
  },

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },

  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})

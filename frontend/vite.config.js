import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), '').API_PROXY_TARGET || 'http://localhost:8080'
  const targetUrl = new URL(target)
  const remoteTarget = !['localhost', '127.0.0.1'].includes(targetUrl.hostname)

  return {
    plugins: [react()],
    server: {
      port: 5174, open: false,
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          configure(proxy) {
            if (!remoteTarget) return
            // Same-origin POSTs carry the local Vite Origin. The remote backend
            // only allows its public origin, so keep the proxied request coherent.
            proxy.on('proxyReq', (proxyRequest) => {
              proxyRequest.setHeader('Origin', targetUrl.origin)
            })
          },
        },
      },
    },
  }
})

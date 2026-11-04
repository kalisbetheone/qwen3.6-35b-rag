import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Dev trên laptop trỏ vào backend Colab: tạo frontend/.env.local với
//   VITE_BACKEND=https://xxxx.trycloudflare.com
// rồi `npm run dev` (proxy /api, khỏi lo CORS).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: env.VITE_BACKEND ? { '/api': { target: env.VITE_BACKEND, changeOrigin: true } } : undefined,
    },
    build: { outDir: 'dist', chunkSizeWarningLimit: 1500 },
  };
});

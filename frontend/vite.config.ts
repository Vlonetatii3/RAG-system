import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // allowedHosts: necesario para servir el build tras el dominio de Railway/Render
  preview: { port: 5173, allowedHosts: true },
});

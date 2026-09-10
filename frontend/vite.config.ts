import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // MapLibre's GeoJSON worker must stay out of Vite's dependency optimizer.
  // Otherwise a dev server can render the raster basemap and DOM markers while
  // failing to load the worker that processes backend-supplied route geometry.
  optimizeDeps: { exclude: ['maplibre-gl'] },
});

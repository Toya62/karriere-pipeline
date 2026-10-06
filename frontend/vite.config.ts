import { defineConfig } from "vite";

// The app is served by FastAPI at /app/, with hashed assets under /app/assets/.
export default defineConfig({
  base: "/app/",
  build: {
    outDir: "../dashboard/app",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/applications": "http://127.0.0.1:8000",
      "/style.css": "http://127.0.0.1:8000",
    },
  },
});

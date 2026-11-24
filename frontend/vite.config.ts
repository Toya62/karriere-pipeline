import { defineConfig, loadEnv } from "vite";

// The app is served by FastAPI at /app/, with hashed assets under /app/assets/.
export default defineConfig(({ mode }) => {
  const envDir = "../";
  const env = loadEnv(mode, envDir, ["VITE_", "GOOGLE_"]);
  const googleClientId =
    env.VITE_GOOGLE_CLIENT_ID ||
    env.GOOGLE_CLIENT_ID ||
    (typeof process !== "undefined" && (process.env.VITE_GOOGLE_CLIENT_ID || process.env.GOOGLE_CLIENT_ID)) ||
    "";

  return {
    base: "/app/",
    envDir,
    build: {
      outDir: "../dashboard/app",
      emptyOutDir: true,
      sourcemap: false,
    },
    define: {
      "import.meta.env.VITE_GOOGLE_CLIENT_ID": JSON.stringify(googleClientId),
    },
    server: {
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8000",
        "/applications": "http://127.0.0.1:8000",
        "/style.css": "http://127.0.0.1:8000",
      },
    },
  };
});

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    env: {
      VITE_GOOGLE_CLIENT_ID: "test-google-client-id.apps.googleusercontent.com",
    },
  },
});

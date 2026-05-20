import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs on :8000 (uvicorn). `/api/*` from the web app is proxied
// there in dev so CORS doesn't get in the way.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});

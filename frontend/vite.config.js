import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// /api is proxied to the bridge API: by nginx inside Docker, by Vite in local dev.
// The port is config.py's BACKEND_PORT, passed in as an env var so one setting
// moves the backend, this proxy and the smoke test together (bugs #40, #85).
const BACKEND_PORT = process.env.BACKEND_PORT || "8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": `http://localhost:${BACKEND_PORT}` },
  },
});

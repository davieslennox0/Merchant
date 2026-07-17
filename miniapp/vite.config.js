import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Allow tunnel hosts (ngrok/localtunnel) when testing the dev server in MiniPay.
    allowedHosts: true,
    proxy: {
      "/api": "http://127.0.0.1:8010",
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server dan preview meneruskan /api ke backend lokal (127.0.0.1 saja, AGENTS.md).
// `Connection: close` ke backend: uvicorn menutup koneksi diam setelah 5 detik, dan Node >= 19 memakai ulang soket
// lama secara default, yang menghasilkan ECONNRESET dan permintaan menggantung.
const proxy = {
  "/api": { target: "http://127.0.0.1:8000", headers: { Connection: "close" } },
};

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy },
  preview: { host: "127.0.0.1", port: 4173, proxy },
});

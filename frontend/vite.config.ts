import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server dan preview meneruskan /api ke backend lokal (127.0.0.1 saja, AGENTS.md).
// `Connection: close` ke backend: uvicorn menutup koneksi diam setelah 5 detik, dan Node >= 19 memakai ulang soket
// lama secara default, yang menghasilkan ECONNRESET dan permintaan menggantung.
const proxy = {
  "/api": { target: "http://127.0.0.1:8000", headers: { Connection: "close" } },
};

// Ekspor statis (M5.1, H-051): `vite build --mode static` (mode "static" menyetel VITE_STATIC=1 saat build). Tanpa backend: UI membaca `data/*.json`
// yang ditulis `python -m backend.replay.export --out dist-static`. base "./" supaya jalan di sub-jalur GitHub Pages.
// Keluaran ke ../dist-static (di luar `frontend/dist`, di-gitignore); `emptyOutDir: false` agar `data/` hasil ekspor tidak terhapus.
export default defineConfig(({ mode }) => {
  const isStatic = mode === "static";
  return {
    plugins: [react()],
    server: { host: "127.0.0.1", port: 5173, proxy },
    preview: { host: "127.0.0.1", port: 4173, proxy },
    ...(isStatic
      ? {
          base: "./",
          define: { "import.meta.env.VITE_STATIC": JSON.stringify("1") },
          build: { outDir: "../dist-static", emptyOutDir: false },
        }
      : {}),
  };
});

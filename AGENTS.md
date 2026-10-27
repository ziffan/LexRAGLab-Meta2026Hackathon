# Instruksi agen — repo app LexRAGLab

Tujuan: aturan wajib untuk setiap agen AI yang bekerja di repo ini.
Sumber keputusan: H-003, H-006, H-007, H-009, H-013, H-016, H-017, H-018, H-028, H-031, H-032, H-037, H-039, H-041, H-046, H-047, H-052, H-053.

Repo ini submission Meta Global AI Developer Hackathon (26 Okt–4 Nov 2026): penemu setting chunking dan retrieval per keluarga dokumen hukum Indonesia. Keputusan lengkap ada di log keputusan operator di luar repo ini (catatan perencanaan pra-acara, tidak disertakan); ringkasannya di `docs/DECISIONS.md`. Kalau dokumen bentrok, keputusan yang menang.

## Baca berurutan

1. `docs/CONTEXT.md` — di mana proyek sekarang
2. `docs/DECISIONS.md` — locked dan pending
3. `docs/ISSUES.md` — pertanyaan terbuka; jangan memutus isu "Menunggu operator"
4. `docs/MILESTONES.md` — slice, kriteria selesai, status
5. Spec slice yang dikerjakan (tabel "Spec per slice" di `docs/MILESTONES.md`)
6. `docs/CONVENTIONS.md` dan `docs/GOTCHAS.md`
7. `docs/PRD.md`, `docs/ARCHITECTURE.md` — referensi saat perlu

Jangan menempel ulang isi dokumen ke chat. Rujuk jalur dan bagian.

## Jangan pernah

- Menulis, mengisi, atau menyetujui butir evaluasi. Butir sah hanya ditulis operator, atau diusulkan Spark lewat pipeline lalu disetujui operator (H-006). Jangan menyebut jumlah butir yang belum ada.
- Mengisi atau mengubah tabel status berlaku (H-009) atau koreksi skema A. Itu milik operator.
- Menulis kode slice Tier 1 sebelum skenario test-nya disetujui operator. Agen menyusun skenario dengan data sintetis, pemeriksa agen independen mengeceknya, operator menyetujui (H-052, `docs/EVAL-SPEC.md` §11). Skenario bukan butir evaluasi: tidak masuk `data/butir/` dan tidak dihitung di laporan.
- Memasukkan akta asli, dokumen internal, data klien, atau data pribadi nyata (H-007). Akta hanya sintetis.
- Menyalin kode prototipe pra-acara operator. Prototipe itu hanya acuan metode, tidak diubah dan tidak di-bundle (H-003).
- Memakai model selain `muse-spark-1.3-contributor` lewat Model API (H-028). Tanpa SAM, Muse Image, atau Wonder (H-019). Model ID hanya dari `config/model`. Muse Code, kalau dipakai, tetap Standard. Pengecualian satu-satunya: Muse Glimmer lokal di mesin operator sebagai pembanding on-prem peran C, stretch (H-047, H-053); model ID, kuantisasi, dan `reasoning_effort` dipin di `config/model` sebelum run, run-nya tidak dicampur dengan run Contributor. Glimmer tidak dipakai untuk A, B, D, verifier, atau penilai. Spark Open tidak dipakai.
- Memakai Chat Completions atau tool calling. Semua panggilan Model API lewat Responses API dengan `strict: true` (H-016). Pengecualian: klien Glimmer lokal (endpoint OpenAI-compatible di `127.0.0.1`) memakai Chat Completions, dengan validasi skema di sisi klien (H-047). Tanpa key kedua, kecuali key OpenRouter untuk dev dan uji (H-057).
- Menambah database, auth, vector database, LangChain, parser PDF, atau reranker (H-013).
- Menulis API key ke kode, log, test, fixture, atau commit. Key hanya di `.env` lokal.
- Mengarang angka (recall, token, biaya, jumlah butir) di README, UI, atau video. Angka hanya dari run tersimpan.
- Memotong peran A, B, C, atau D, atau waktu video. Garis potong yang sah hanya H-017.
- Menjalankan panggilan Spark berulang tanpa cache, atau batch tanpa proyeksi biaya.
- Mengunci isu di `docs/ISSUES.md` tanpa keputusan operator.

## Kontrak eksekutor per slice

Prompt setiap slice memuat:
- Pointer ke `docs/MILESTONES.md` slice terkait dan keputusan terkait. Pointer, bukan salinan.
- Slice, kriteria selesai, scope file, dan larangan file (kolom "Di luar scope").
- Perintah menulis test-nya juga, dan menyetor bukti (output test, screenshot, catatan run), bukan klaim.
- Untuk slice Tier 1 (M0.1, M1.2, M1.4, M1.5, M2.1, M2.3, M2.4, M3.2, M4.3), skenario test yang sudah disetujui operator (H-052).
- Larangan tetap di atas.

Penulis kode tidak memeriksa karyanya sendiri. Review sesuai tier di slice.

## Aturan teknis singkat

- Nilai yang bisa berubah di `config/` berversi (`docs/ARCHITECTURE.md` §7).
- Setiap run mencatat `RunRecord` (`docs/DATA-CONTRACTS.md` §12). Hasil disimpan per hash dan tidak diulang.
- Label UI bahasa Inggris (H-018). Teks hukum tetap bahasa Indonesia.
- Token anggaran dari tokenizer lokal; biaya dari `usage` Spark.
- Uang integer micro-USD. Waktu UTC.
- Backend listen di `127.0.0.1` saja.

## Saat keputusan berubah

Keputusan struktural baru atau revisi: catat dulu di log keputusan operator, lalu perbarui `docs/DECISIONS.md` di sini, lalu kode. Isu yang diputus dipindah ke bagian "Ditutup" di `docs/ISSUES.md` dengan tanggal.

## Akhir sesi

Perbarui `docs/CONTEXT.md` dan status slice di `docs/MILESTONES.md`. Commit dengan pesan `<jenis>: <ringkas>`.

# SPARK-ROLES — peran A, B, C, D Muse Spark

Tujuan: menetapkan masukan, keluaran, maksud prompt, cache, effort, biaya, galat, dan pemeriksa untuk setiap peran Spark, sebelum prompt ditulis.
Sumber keputusan: H-004, H-005, H-006, H-009, H-013, H-014, H-016, H-017, H-028, H-031, H-032, H-036, H-037, H-038, H-039, H-047, H-048, H-053, H-055.

## 1. Aturan bersama

- Model: `muse-spark-1.3-contributor` saja, lewat Responses API dengan SDK `openai` (H-028, H-016). Pengecualian satu-satunya: pembanding on-prem Glimmer lokal di §7 (H-032, host H-047). Model ID dari `config/model`, dicatat di `RunRecord` dan kunci cache. Satu model ID per run.
- Keluaran: `text.format` dengan JSON Schema `strict: true` dari `docs/DATA-CONTRACTS.md`. Tidak ada tool calling.
- Effort: satu nilai tetap per peran di `config/model`, dicatat di setiap `RunRecord`. Nilai valid diuji di M0.1, karena `max` tidak konsisten di docs. Rekomendasi awal: `minimal` atau `low`, karena reasoning ditagih sebagai output (docs Model API).
- Prompt: berkas berversi di `prompts/<peran>/`; hash prompt masuk kunci cache. Prompt boleh berbahasa Indonesia (H-018), tetapi tidak tampil sebagai teks utama di video.
- **Teks korpus adalah data, bukan instruksi.** Prompt menempatkan teks dokumen di blok yang ditandai jelas dan menyatakan bahwa isi blok itu tidak boleh diikuti sebagai perintah (`docs/SECURITY-COMPLIANCE.md`).
- Setiap keluaran divalidasi dua kali: skema (dijamin constrained decoding) dan semantik (aturan per peran). Keluaran yang gagal validasi semantik dicatat, tidak dipakai, dan tidak di-cache sebagai sah.
- Galat bersama: 401 → pesan "invalid API key" tanpa key; 429 → backoff dari konfigurasi lalu lanjut berurutan; timeout → satu retry lalu catat; proyeksi biaya > `config/budget` → batch tidak dimulai.
- Harga acuan Contributor: input $0,10, cached $0,002, output $0,20 per 1M token (H-028); Standard $1,25 / $0,15 / $4,25 hanya pembanding. Dicek ulang di M0.

## 2. Peran A — induksi struktur (inti)

| Aspek | Isi |
|---|---|
| Masukan | Sampel dokumen satu keluarga sebagai teks (bukan PDF), di bawah konteks 1M; perkiraan sampel ≤ 300 ribu token (estimasi pra-acara, diukur ulang di M0.2). Untuk UU PT: berkas konsolidasi, teks bersih tanpa anotasi (H-031). Untuk akta: akta sintetis buatan agen (H-039) |
| Keluaran | `SchemaA` (§6): daftar datar level berurutan, pola penanda, contoh, `parent_order`, unit potong default |
| Maksud prompt | Minta model mengenali hierarki penanda yang berulang di keluarga itu (mis. BAB, Pasal, ayat; atau kepala, badan, penutup akta) dan menuliskannya sebagai pola yang bisa dijalankan chunker deterministik, dengan contoh yang dikutip persis dari sampel |
| Batasan prompt | Tidak boleh memberi skema contoh UU PT saat menginduksi akta (supaya transfer jujur). Contoh harus dikutip dari sampel, bukan dikarang. Tanpa rekursi; hierarki lewat `parent_order` |
| Validasi semantik | Setiap `marker_pattern` dikompilasi dan diuji terhadap `examples`-nya sendiri; contoh harus ditemukan di sampel |
| Cache | Sampel di awal pesan sebagai prefix tetap; kunci cache hasil per hash sampel + prompt + model + effort. Beberapa panggilan per keluarga saja |
| Perkiraan biaya | Contributor < $0,50 per keluarga (estimasi pra-acara) |
| Pemeriksa | Operator mengoreksi skema menjadi v2 lewat editor U5 (H-037, Tier 4 domain review; fallback berkas berversi bila pemicu 31 Okt aktif, H-055). Pada UU PT, skema dibandingkan dengan parser tulisan tangan lewat selisih batas (M3.4) |
| Slice | M3.3, M3.4, M4.1 |

## 3. Peran B — contextual chunking (inti)

| Aspek | Isi |
|---|---|
| Masukan | Satu dokumen sumber utuh sebagai prefix tetap + satu potongan (alamat dan teks) per panggilan |
| Keluaran | `HeaderB` (§7): `chunk_id` dan teks header |
| Maksud prompt | Tulis header singkat yang menempatkan potongan dalam dokumennya (peraturan, bab, pokok pengaturan) supaya potongan bisa ditemukan oleh query yang tidak berbagi kata dengannya |
| Batasan prompt | Header tidak boleh menyalin isi gold atau menjawab pertanyaan; tidak boleh menyebut peraturan lain yang tidak ada di dokumen. Panjang header dibatasi konfigurasi, karena tokennya masuk anggaran (H-004) |
| Validasi semantik | `chunk_id` sama dengan yang diminta; panjang header dalam batas |
| Cache | Dokumen di awal pesan, tidak berubah antar-panggilan. Satu request pemanas, lalu `prompt_cache_key` per dokumen. Cached tokens dibaca dari `usage.input_tokens_details.cached_tokens`. Panggilan berurutan, bukan paralel |
| Granularitas | Per pasal, per ayat, atau hanya setting di frontier: diputus operator dari angka M3.1 (H-038). Bila M2 belum selesai 31 Okt malam: otomatis hanya setting di frontier |
| Perkiraan biaya | Contributor: korpus per pasal < $1, per ayat sekitar $2–4 (estimasi pra-acara, batas atas). Waktu pada 150 RPM menjadi kendala. Diukur ulang di M3.1 sebelum dijalankan penuh |
| Pemeriksa | Sistem (validasi); operator membaca sampel header di M3.1. Dampak header diukur di frontier, bukan dinilai LLM |
| Slice | M3.1, M3.2 |

## 4. Peran C — evaluasi ujung ke ujung (lantai bukti)

| Aspek | Isi |
|---|---|
| Masukan | Query butir + potongan terambil dari satu profil (`P`, bagian 3 `docs/EVAL-SPEC.md`), masing-masing dengan label alamat. Anggaran dan instruksi sistem sama untuk profil terbaik dan pembanding. Anggaran konteks = token teks sumber; label alamat tidak dihitung dan diberikan sama ke semua chunker (H-066). Token input aktual tampil per kolom di U3 |
| Keluaran | `AnswerC` (§8): `status` (`jawab`/`tolak`/`bukti_tidak_cukup`), `jawaban`, `kutipan[]` berisi `alamat` dan `teks` |
| Maksud prompt | Jawab hanya dari konteks yang diberikan. Setiap klaim dikutip dengan teks yang disalin persis dan alamat **unit** (mis. `… › Pasal n › ayat (m)`) yang disalin dari label konteks; bila label potongan berbentuk rentang `A – B`, kutipan menyalin alamat unit tempat teks berada, bukan label rentang (H-067, V5 (i): verifier uji 1 strict menolak rentang; prompt C M2.2 berubah). Bila konteks tidak memuat jawabannya, tolak atau nyatakan bukti tidak cukup; itu keluaran sah |
| Batasan prompt | Tidak boleh memakai pengetahuan di luar konteks. Tidak boleh tahu profil mana yang sedang dijawab (instruksi identik, tanpa nama setting) |
| Validasi semantik | Status `jawab` dengan kutipan kosong ditandai; penilaian kutipan oleh verifier, bukan LLM |
| Cache | Kunci per hash konteks + prompt + provider + model + kuantisasi + effort. Hasil disimpan; replay tidak memanggil API |
| Pilihan model | Default Contributor. Pembanding Glimmer lokal lewat `model_profile` di W6 (§7, H-053) |
| Perkiraan biaya | Contributor < $0,50 untuk 20 butir × 2 profil × beberapa ulangan (estimasi pra-acara) |
| Pemeriksa | Verifier deterministik uji 1–2 (uji 3 stretch, H-017). Penilaian utama tetap kecocokan dengan gold operator. Butir adegan video dicek manual (H-011) |
| Slice | M2.2, M2.3, M2.4 |

## 5. Peran D — usulan butir (pendukung)

| Aspek | Isi |
|---|---|
| Masukan | Satu dokumen sumber + mode yang diminta (`literal`, `parafrase`, `unanswerable`) |
| Keluaran | `ProposalD` (§9): daftar `{query, mode, doc_id, teks_gold, start, end}`; mode `unanswerable` (H-092 akta; H-095, H-099 juga UU PT): `ProposalU`, daftar `{query, doc_id, alasan_kode, alasan_teks}` tanpa span |
| Maksud prompt | Usulkan pertanyaan yang jawabannya ada di span dokumen yang mencakup semua ayat yang dibutuhkan, tidak lebih (H-048), dengan span dikutip persis. Mode parafrase wajib: pertanyaan tidak boleh berbagi kata kunci literal dengan span (melawan bias BM25, H-006) |
| Batasan prompt | Span harus dikutip persis dari dokumen. Tidak boleh mengusulkan pertanyaan yang jawabannya butuh dokumen lain. Jumlah usulan per panggilan dibatasi konfigurasi |
| Validasi semantik | Sistem mencari `teks_gold` di dokumen; offset Spark (bila ada) harus cocok. Hasilnya ditampilkan di layar Review (`offset found`, `text matches`) |
| Cache | Kunci per hash dokumen + mode + prompt. Dokumen sebagai prefix tetap |
| Mode `unanswerable` (H-087, H-092) | Prompt `prompts/d/v2.md` (hanya mode ini; v1 tetap untuk `literal`/`parafrase`): 2-3 pertanyaan wajar untuk akta yang jawabannya tidak ada (kandidat baik: data tidak dimuat H-041 seperti NIK/NPWP/rekening, fakta di luar akta, rincian tidak diatur; kandidat buruk: jawaban tersirat), tanpa span, dengan `alasan_kode` + `alasan_teks`. Batas keras `max_per_call = 3`. Sistem memeriksa lokal (BM25/dense top-K atas potongan skema A aktif) dan menandai kandidat meragukan; butir lahir `mode = tolak` hanya lewat persetujuan operator. Proyeksi batch: `python -m backend.proposal unanswerable --family akta --project-only`, faktor ulang G-36 `factor_bp` di `config/budget [batch_gate]` (asumsi) |
| Mode `unanswerable` UU PT (H-095, H-099 V1-V3, V9) | Prompt `prompts/d/v3.md` khusus keluarga `uupt` (dipilih lewat `by_family_mode` di `prompts/d/versions.json`; v2 tetap untuk akta, v1 untuk mode ber-span; teks v3 ditinjau operator sebelum `--run`). Skema `ProposalU` dan enum `alasan_kode` sama; makna untuk UU PT: `data_tidak_dimuat` = data perusahaan/orang tertentu yang tidak ada di UU, `di_luar_akta` = di luar dokumen (aturan lain, peristiwa sesudah UU, putusan), `rincian_tidak_diatur` = diserahkan ke peraturan pelaksana atau tidak diatur. Unit pemeriksaan = potongan skema A UU PT aktif. Batas `max_per_call` (3) atau `max_per_call_uupt` bila diisi (H-099 Q1 a1). Proyeksi: `python -m backend.proposal unanswerable --family uupt --project-only` (satu panggilan per dokumen UU PT, gerbang yang sama) |
| Perkiraan biaya | Contributor < $0,50 untuk beberapa puluh usulan (estimasi pra-acara) |
| Pemeriksa | **Operator memeriksa setiap usulan** dan menyetujui, mengubah, atau menolak (H-006). Agen pengembang tidak menyetujui butir. Hasil dilaporkan per asal |
| Slice | M2.1, M4.2 |

## 6. Ringkasan

| Peran | Status | Slice | Biaya (estimasi pra-acara) | Pemeriksa |
|---|---|---|---|---|
| A | Inti | M3.3, M3.4, M4.1 | < $0,50 | Operator (koreksi v2) + selisih batas |
| B | Inti | M3.1, M3.2 | Contributor: per pasal < $1, per ayat sekitar $2–4 (H-028); granularitas H-038 | Sistem + frontier |
| C | Lantai bukti | M2.2–M2.4 | < $0,50 | Verifier deterministik + gold operator |
| D | Pendukung | M2.1, M4.2 | < $0,50 | Operator, setiap usulan |

Wonder tidak dipakai di peran mana pun; lihat H-019.

## 7. Pembanding on-prem: Glimmer lokal pada peran C (stretch, H-047, H-053)

| Aspek | Isi |
|---|---|
| Tujuan | Menunjukkan bahwa profil setting tetap berguna untuk model open-weight yang benar-benar berjalan di mesin sendiri (skenario dokumen rahasia) |
| Model | Muse Glimmer lokal di mesin operator (LM Studio, endpoint OpenAI-compatible di `127.0.0.1`). Model ID, kuantisasi `Q4_K_M`, dan `reasoning_effort` `high` di `config/model`, dipin sebelum run dan tidak diubah setelah melihat hasil. Reasoning tidak bisa dimatikan (G-26) |
| Peran | Hanya C: profil terbaik dan baseline H-036 dijalankan ulang dengan prompt, anggaran, dan konteks yang sama. Tidak untuk A, B, D, verifier, atau penilai. Pembanding peran C tetap setting `fixed_size` (H-036) |
| Jalur | W6 dengan `model_profile` Glimmer; U3 menampilkan pemilih model dan label model, kuantisasi, effort (H-053). Bila server lokal mati, pilihan nonaktif |
| Klien | Chat Completions lokal (Responses API hanya untuk Model API Meta, H-016), validasi skema di sisi klien. Tanpa key kedua |
| Pencatatan | `RunRecord.provider = lmstudio_local`, `model`, `quantization`, `effort`; `AnswerRecord.model_profile`. Run Glimmer tidak dicampur dengan run Contributor dalam satu frontier atau perbandingan tanpa label (H-028) |
| Jadwal | Stretch, hanya setelah lantai H-017 aman. Glimmer dan embedding tidak dijalankan bersamaan (VRAM) |
| Klaim | Glimmer disebut open-weight yang berjalan di mesin operator, bukan bobot yang sama dengan Spark. Tanpa klaim mutu bahasa Indonesia umum. Klaim bonus open-weight hanya setelah cara verifikasi "own hardware" dikonfirmasi penyelenggara. Atribusi mengikuti kartu model |
| Slice | M2.5 (stretch) |

Spark Open (lewat OpenRouter atau Baseten) tidak dipakai (H-047).

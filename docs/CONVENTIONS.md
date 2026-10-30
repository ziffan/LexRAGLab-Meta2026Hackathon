# CONVENTIONS — konvensi kerja repo app

Tujuan: aturan penamaan, bahasa, data, commit, dan test yang berlaku di semua slice.
Sumber keputusan: H-005, H-013, H-014, H-016, H-018, H-031, H-045, H-052, H-102, H-103.

## Bahasa

- Dokumen spec: bahasa Indonesia, istilah teknis Inggris dibiarkan.
- `README.md`, label UI, pesan galat yang tampil, dan narasi video: bahasa Inggris (H-018).
- Enum data: nilai bahasa Indonesia sesuai keputusan (`jawab`, `spark_disetujui`); label UI lewat `docs/UI-SPEC.md` §6.
- Prompt Spark boleh bahasa Indonesia.

## Data

- Offset = code point, setengah terbuka. Hash = SHA-256 heks. Waktu = UTC ISO 8601. Uang = integer micro-USD (`docs/DATA-CONTRACTS.md` §1).
- Data milik operator (butir, tabel status, koreksi skema) diberi versi dan tidak ditimpa.
- Nilai yang bisa berubah ada di `config/`, bukan literal di kode.

## Kode

- Backend: Python 3.12, FastAPI. Frontend: React + TypeScript + Vite (H-013). Versi dipin di M0.
- Satu modul per komponen di `docs/ARCHITECTURE.md` §4. Kalkulator metrik dan verifier tanpa I/O jaringan.
- Galat ke UI berbentuk `{error: {code, message}}`, tanpa stack trace dan tanpa key.
- Log tidak pernah memuat key, header otorisasi, atau teks akta lengkap.

## Test

- Setiap slice menulis test-nya sendiri dan menyetor output test, bukan klaim.
- Slice Tier 1: skenario disusun agen dengan data sintetis sebelum kode, dicek pemeriksa agen independen, disetujui operator (H-052, `docs/EVAL-SPEC.md` §11; kecuali skenario delta yang persetujuannya didelegasikan operator, H-102/H-103).
- Test tidak memanggil Model API. Panggilan Spark diuji dengan run tersimpan.

## Git

- Commit pertama setelah 26 Okt 2026 23:00 WIB. Isinya `.gitattributes` dan `.editorconfig` (bagian "Akhir baris"), sebelum berkas lain.
- Pesan commit: `<jenis>: <ringkas>` (`feat`, `fix`, `test`, `docs`, `chore`). Satu slice, satu atau beberapa commit, status di `docs/MILESTONES.md` diperbarui di commit terakhir slice.
- `.env`, cache embedding besar, dan tokenizer berlisensi tidak di-commit.

## Akhir baris (GOTCHAS G-16)

Dev berjalan di dua mesin: mesin Windows (Git for Windows memasang `core.autocrlf=true` di level sistem) dan mesin Linux. Offset span gold dan hash korpus bergantung pada byte, jadi akhir baris wajib LF di semua mesin.

- `.gitattributes` di root, commit pertama:

  ```text
  * text=auto eol=lf
  data/** -text
  *.npy binary
  *.png binary
  *.ico binary
  ```

  `eol=lf` mengalahkan `core.autocrlf` mesin mana pun. `data/** -text` membuat git tidak pernah menyentuh byte korpus, butir, akta, dan status.
- `.editorconfig` di root: `[*]` `end_of_line = lf`, `charset = utf-8`, `insert_final_newline = true`.
- Clone di mesin Windows: `git clone -c core.autocrlf=false <url>` (pengaman kedua; atribut repo tetap yang utama).
- Python yang menulis berkas ke repo atau `runs/`: `open(..., 'w', encoding='utf-8', newline='\n')`. Membaca korpus: mode biner lalu decode UTF-8, bukan mode teks (mode teks Python menerjemahkan `\r\n` diam-diam).
- Corpus loader menolak berkas yang memuat `\r` atau BOM, dan menolak hash yang tidak cocok dengan `config/corpus` (UU PT: SHA-256 `a6b38ee5…`, H-045, diverifikasi di M0.2).

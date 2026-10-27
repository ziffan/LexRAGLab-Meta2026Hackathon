# Brief akta sintetis (H-039, H-041)

Status: **disetujui operator 27 Okt 2026 apa adanya** (lewat orkestrator, I-46 ditutup). Brief operator untuk H-039.

Disusun agen dari kerangka `docs/MILESTONES.md` M4 (prasyarat) dan `docs/SECURITY-COMPLIANCE.md` T4; disetujui operator tanpa perubahan.

## Isi brief

1. **Jenis dan jumlah**: lima akta pendirian Perseroan Terbatas (bahasa Indonesia), satu berkas teks per akta di `data/akta/`, LF, UTF-8, tanpa BOM.
2. **Kerangka (Pasal 38 UU 2/2014)**:
   - Kepala akta: judul, nomor akta, jam/hari/tanggal/bulan/tahun, nama lengkap dan kedudukan notaris.
   - Badan akta: komparisi (identitas penghadap), keterangan kedudukan bertindak, isi akta berupa anggaran dasar dalam "Pasal n" yang mengikuti muatan Pasal 15 UU 40/2007 (nama dan tempat kedudukan; maksud, tujuan, kegiatan usaha; jangka waktu; modal dasar, ditempatkan, disetor; saham; direksi dan dewan komisaris; RUPS; penggunaan laba; ketentuan lain), dan keterangan saksi pengenal bila ada.
   - Akhir/penutup akta: uraian pembacaan, penandatanganan, nama saksi akta, uraian perubahan (renvoi) bila ada.
3. **Variasi supaya batas bagian teruji**: jumlah Pasal anggaran dasar berbeda antar akta (mis. 14, 17, 20, 22, 25); dua dari lima tanpa saksi pengenal; satu dengan renvoi di penutup; satu dengan susunan pemegang saham lebih dari dua; penomoran Pasal tetap "Pasal n" dengan ayat "(n)" di sebagian Pasal saja.
4. **Identitas (H-041)**: semua nama orang, notaris, PT, alamat fiktif dan dihindarkan dari kesamaan dengan pihak nyata (agen memeriksa tidak memakai nama tokoh/perusahaan terkenal; pakai nama generik dengan kombinasi tak lazim). **Tanpa NIK**, tanpa nomor KTP/NPWP/telepon/rekening. Nomor akta dan tanggal fiktif (tahun 2025–2026). Nilai modal integer rupiah fiktif.
5. **Disclaimer per akta**: baris pertama berkas `[SINTETIS — dokumen fiktif untuk uji LexRAGLab; tidak berlaku hukum; identitas rekaan]` (bahasa Indonesia), juga di README.
6. **Larangan**: tidak menyalin akta asli, template kantor, atau blanko PPAT (H-056); tidak memakai prototipe pra-acara (H-003); tidak memakai skema UU PT sebagai acuan struktur di prompt A (transfer jujur, SPARK-ROLES §2).
7. **Review operator**: setiap berkas diperiksa operator (identitas fiktif, tanpa NIK, kewajaran hukum) sebelum dipakai di run yang dilaporkan (addendum 2 gerbang 4).
8. **Panjang**: tiap akta kira-kira 2.000–4.000 kata; total di bawah 30K token lokal (sampel induksi A akta).

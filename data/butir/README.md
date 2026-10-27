# data/butir

Butir evaluasi (`Item`, `docs/DATA-CONTRACTS.md` §4), JSONL satu butir per baris, satu berkas per keluarga dan versi. Versi tidak ditimpa; penambahan butir menjadi versi baru.

| Berkas | Isi |
|---|---|
| `uupt.v1.jsonl` | Sembilan butir kontrol UU PT (`origin: operator`, H-011): query, span, dan mode ditulis operator; offset atas teks bersih `clean_sha256` `c56e4f0f38a4…` dihitung dari alamat yang ditulis operator, lalu disetujui operator 27 Okt 2026. Satu butir wajib tolak (`gold_spans: []`). Validator jalur masuk menyusul di M1; sampai itu ada, berkas ini belum tervalidasi otomatis |

# EVAL-SPEC — definisi metrik, anggaran, split, frontier, dan verifier

Tujuan: mendefinisikan secara formal setiap angka yang menentukan "optimal", supaya kalkulator ditulis dari definisi, bukan sebaliknya.
Sumber keputusan: H-005, H-006, H-009, H-011, H-012, H-014, H-015, H-017, H-031, H-033, H-034, H-036, H-046, H-048, H-049, H-052, H-054, H-055.

Metode mengacu pada karya pra-acara operator; tidak ada kode yang disalin (H-003).

Status definisi: semua definisi yang semula bertanda [usulan] dikunci operator 26 Okt (H-033). Pemecah seri dilengkapi H-034 dan H-055. Recall@K dan aturan penulisan span gold diperjelas H-048. Porsi held-out H-049. Keluarga akta tanpa split (H-054).

## 1. Notasi

| Simbol | Arti |
|---|---|
| `q` | satu butir (`Item`) |
| `D` | teks dokumen gold, sebagai urutan code point |
| `G` | himpunan posisi karakter di semua `gold_spans` butir |
| `C = (c1, c2, …)` | ranking potongan untuk `q` dari satu setting |
| `P ⊆ C` | potongan yang terambil setelah pengemasan anggaran (bagian 3), berurutan |
| `chars(c)` | himpunan posisi karakter `[start, end)` potongan `c` |
| `tok(x)` | jumlah token lokal teks `x` (H-014) |
| `hdr(c)` | teks header B potongan `c`, kosong bila header off |
| `B` | anggaran token konteks |

## 2. Tokenizer dan kalibrasi (H-014)

- Semua `tok(·)` memakai satu tokenizer lokal deterministik untuk semua setting. Pilihan pertama: tokenizer Muse Spark Open dari HF. Cadangan: `o200k`.
- Nama dan versi tokenizer dicatat di setiap `RunRecord`.
- Kalibrasi sekali di M0.2: untuk setiap dokumen, `rasio = tokens_endpoint / tokens_local`, dengan `tokens_endpoint` dari `/v1/responses/input_tokens` dikurangi baseline input kosong. Rasio per dokumen (UU PT juga per `section`) dan rata-rata disimpan di `config/tokenizer`.
- Rasio hanya informasi. Anggaran dan precision tetap dihitung dengan token lokal.
- Biaya dihitung dari `usage` Spark, tidak pernah dari token lokal.
- Setiap angka token di layar dan video diberi label "local tokenizer".

## 3. Pengemasan anggaran token

Biaya satu potongan: `cost(c) = tok(hdr(c)) + tok(teks c)`. Token header ikut anggaran (H-004).

Aturan:
1. Telusuri `C` berurutan. Akumulasi `cost`.
2. Potongan dimasukkan ke `P` selama akumulasi ≤ `B`.
3. Potongan pertama yang akan melewati `B` ditangani menurut `config/grid.packing`:
   - `stop` **(default, H-033 a)**: berhenti; potongan itu dan seterusnya tidak ikut.
   - `skip`: lewati potongan itu, lanjut ke potongan berikutnya yang masih muat.
   - `truncate`: potong teks potongan itu sampai anggaran tepat habis; offset akhir disesuaikan.
4. Aturan yang dipakai dicatat di `RunRecord.packing` dan `Profile.packing`.

`stop` dipilih karena tidak menguntungkan potongan kecil secara buatan. `skip` mengisi anggaran lebih penuh tetapi mengubah urutan relevansi.

## 4. Span recall

```text
covered(q) = G ∩ ( ∪_{c ∈ P} chars(c) )
span_recall(q) = |covered(q)| / |G|
```

- Overlap antar potongan tidak dihitung dua kali di pembilang (gabungan himpunan).
- Butir tanpa gold (`G = ∅`): `span_recall = null`, dilaporkan terpisah sebagai "no gold (must abstain)".
- `fully_covered(q)` = `covered(q) = G`.
- Agregat setting: rata-rata `span_recall` atas butir dengan gold, plus hitungan `fully_covered` "x of y".

## 5. Precision token

Setiap potongan di `P` ditokenisasi dengan offset karakter. Satu token adalah **token gold** bila seluruh karakternya ada di `G`. Token header tidak pernah token gold.

```text
retrieved_tokens(q) = Σ_{c ∈ P} cost(c)            (termasuk duplikasi overlap dan header)
gold_tokens(q)      = jumlah token gold atas posisi unik di covered(q)
token_precision(q)  = gold_tokens(q) / retrieved_tokens(q)
```

- Duplikasi karena overlap menambah penyebut, tidak menambah pembilang. Ini sengaja menghukum konteks berulang ("tidak berisik", H-005).
- `retrieved_tokens = 0` → `token_precision = null`.
- Butir tanpa gold: `token_precision = null`, dilaporkan terpisah.

## 6. MRR dan Recall@K

- `rank(q)` = posisi (mulai 1) potongan pertama di `P` yang `chars(c) ∩ G ≠ ∅`. Tidak ada → `RR = 0`.
- `reciprocal_rank(q) = 1 / rank(q)`. MRR = rata-rata atas butir dengan gold.
- **Bagian-ayat gold (H-048).** Sebelum metrik dihitung, sistem memecah setiap span gold di batas ayat batang tubuh menjadi bagian-ayat `g1, g2, …`. Pasal tanpa ayat adalah satu bagian. Span di Penjelasan dipecah di batas penanda `Ayat (n)` Penjelasan bila ada. Batas ayat diambil dari peta alamat (alamat kanonik, `docs/DATA-CONTRACTS.md` §2). Untuk akta, pemecahan memakai level ayat di peta alamat akta bila ada; bila tidak, span adalah satu bagian. Pemecahan diuji di kalkulator metrik (Tier 1).
- `Recall@K(q)` = porsi bagian-ayat gold yang **masing-masing seluruhnya** terkandung di salah satu potongan di antara K teratas `C` (boleh potongan berbeda untuk bagian berbeda; tanpa batas anggaran). K dari `config/retrieval`. Definisi ini mengikuti semantik substring yang dijanjikan di form, dan sengaja berbeda dari span recall.

```text
parts(q)     = bagian-ayat semua gold_spans q
Recall@K(q)  = |{g ∈ parts(q) : ∃ c ∈ C[1..K], chars(g) ⊆ chars(c)}| / |parts(q)|
```

- Span recall (§4) dan precision token (§5) tidak berubah oleh pemecahan, karena keduanya dihitung per karakter dan per token.

## 7. Metrik mutu potongan (janji form)

Dihitung per setting atas seluruh potongan korpus keluarga, bukan per butir.

**Entity preservation**

```text
E = kemunculan entitas hukum di korpus, dideteksi pola di config/retrieval.entity_patterns
    (rujukan "Pasal n", "ayat (n)", nama peraturan, tanggal, angka bernilai)
entity_preservation = |{e ∈ E : e seluruhnya di dalam satu potongan}| / |E|
```

**Boundary coherence**

```text
Bnd = semua batas potongan (posisi end yang bukan akhir dokumen)
ok(b) = b jatuh di batas struktur (peta alamat) atau di akhir kalimat (pola di konfigurasi)
boundary_coherence = |{b ∈ Bnd : ok(b)}| / |Bnd|
```

Kasus uji wajib (dari `docs/MILESTONES.md` M1.5): nomor pasal terbelah, batas di tengah kalimat.

## 8. Split berstrata (H-015, H-049)

Berlaku untuk UU PT. Keluarga akta tidak dibagi tune/held-out (H-054): kelima butir akta dilaporkan per butir sebagai uji transfer, dan tidak ada `SplitRecord` akta.

1. Strata = pasangan (`origin`, `mode`).
2. Di tiap stratum, butir diurutkan menurut `id`, diacak dengan `seed` dari `config/grid`, lalu dibagi menurut `held_out_ratio = 0.4` dari `config/grid` (H-049).
3. Syarat keras: minimal tiga butir `operator` ada di held-out. Bila pembulatan per stratum membuat kontrol di held-out kurang dari tiga, butir kontrol dipindahkan ke held-out lebih dulu sampai syarat terpenuhi; aturan ini diuji (Tier 1). Bila tetap tidak bisa terpenuhi (kontrol kurang dari tiga), split gagal dengan pesan jelas, bukan diacak ulang diam-diam.
4. Split ditetapkan sekali. `SplitRecord.assignments` lama tidak pernah berubah.
5. Butir yang disetujui belakangan masuk dengan aturan stratum yang sama, `split_version` naik.
6. Butir held-out **DILARANG** dipakai untuk memilih setting.

Dengan 15–20 butir UU PT, held-out sekitar 6–8 butir dan tune 9–12 (H-015, H-049).

## 9. Frontier, pemilihan, dan laporan

**Dominasi.** Titik `p` mendominasi `r` bila `mean_span_recall(p) ≥ mean_span_recall(r)` dan `mean_retrieved_tokens(p) ≤ mean_retrieved_tokens(r)`, dengan minimal satu ketidaksamaan tegas. Titik yang didominasi tidak masuk frontier.

**Pemilihan.** Untuk UU PT dan per anggaran, profil terbaik dipilih di **tune**: span recall rata-rata tertinggi. Bila seri atau selisihnya ≤ 1 butir, pilih setting paling sederhana: tanpa header B, overlap lebih kecil, satu mode retrieval (H-034); urutan "sederhana" ditulis eksplisit di `config/grid`. Bila masih seri, dipecah token precision, lalu token lebih sedikit (H-033). Bila masih seri, dipilih `setting_id` terkecil secara leksikografis (H-055), sehingga pemilihan selalu deterministik. Keluarga akta tidak punya pemilihan: profil yang diuji di akta adalah profil terbaik UU PT dengan chunker dari skema A akta (H-054).

**Pembanding.** Profil pembanding untuk C adalah setting `fixed_size` yang ditetapkan di `config/grid.baseline`, dengan mode retrieval dan anggaran yang sama dengan profil terbaik (H-036).

**Laporan.** Untuk UU PT, angka yang dilaporkan berasal dari **held-out**, per butir, dipecah per asal dan per mode. Untuk akta, semua butir dilaporkan per butir sebagai uji transfer; laporan dan frontier akta tidak menyebut "held-out" dan tidak mengklaim pemilihan profil (H-054). Tanpa klaim signifikansi (H-005). Hitungan mentah ("x of y"), bukan persen.

**Format laporan per butir**

| Kolom | Sumber |
|---|---|
| item id, origin, mode, split (UU PT) atau `transfer` (akta) | `Item`, `SplitRecord` |
| span recall (pembilang/penyebut karakter) | §4 |
| token precision (pembilang/penyebut token) | §5 |
| reciprocal rank | §6 |
| Recall@K | §6 |
| catatan "no gold (must abstain)" | §4 |

Baris ringkas: hasil per asal (`operator` vs `spark_disetujui`) untuk membaca circularity (H-006).

## 10. Verifier peran C

| Uji | Definisi | Hasil |
|---|---|---|
| 1. Exists | `kutipan.alamat` sama persis dengan salah satu alamat unit di peta alamat keluarga itu (UU PT: parser struktur tulisan tangan, alamat kanonik dengan bagian; akta: `SchemaA` versi aktif). Nomor benar dengan bagian salah = gagal | `lulus` / `gagal` |
| 2. Faithful | `kutipan.teks` adalah substring persis teks sumber di alamat itu; bila tidak, skor fuzzy ≥ ambang `config/verifier` | `lulus` / `gagal`, `faithful_score` |
| 3. Valid on date (stretch, H-017) | status pasal pada `Item.reference_date` menurut `StatusTable` versi yang disetujui operator | `berlaku` / `dicabut` / `berlaku_bersyarat` / `tidak_dijalankan` |

- Uji 2 hanya dijalankan bila uji 1 lulus.
- `berlaku_bersyarat` ditampilkan apa adanya, tidak dipaksa lulus atau gagal (H-009).
- Uji 3 `tidak_dijalankan` bila stretch tidak dikerjakan, tabel belum disetujui, atau `reference_date = null`.

**Ringkasan 2×2 penolakan**, per profil, hitungan mentah:

| Sel | Definisi |
|---|---|
| Answered, supported | `status = jawab`, minimal satu kutipan, semua kutipan lulus uji 1 dan 2, dan minimal satu kutipan berada di potongan yang beririsan dengan `G` |
| Answered, unsupported | `status = jawab` dan syarat di atas tidak terpenuhi, termasuk menjawab butir tanpa gold |
| Abstained, correctly | `status ∈ {tolak, bukti_tidak_cukup}` dan (`G = ∅` atau tidak ada karakter gold di konteks) |
| Abstained, should have answered | `status ∈ {tolak, bukti_tidak_cukup}` dan ada karakter gold di konteks |

Kegagalan "menjawab yakin dari potongan yang salah" tampil apa adanya di sel kedua.

## 11. Skenario test Tier 1

Prosedur (H-052): untuk setiap slice Tier 1, **agen menyusun skenario test dengan data sintetis sebelum kode slice itu ditulis**. Pemeriksa agen independen (bukan penulis kode slice) mengeceknya, lalu operator menyetujuinya di review Tier 1. Kode slice tidak ditulis sebelum persetujuan itu.

- Skenario bukan butir evaluasi (H-006 tetap): memakai teks sintetis atau potongan korpus dengan span buatan test, tidak masuk `data/butir/`, dan tidak dihitung di laporan.
- Setiap skenario memuat masukan, jawaban hitung tangan, dan alasan singkat.
- Ambang fuzzy verifier M2.3 diusulkan dengan alasan tertulis dan disetujui operator.

Slot di bawah sengaja kosong sampai skenario slice itu disusun.

| Slice | Yang diuji | Skenario (diusulkan agen) | Jawaban hitung tangan | Dicek pemeriksa / disetujui operator / tanggal |
|---|---|---|---|---|
| M0.1 | Secret dan perhitungan biaya | `docs/scenarios/M0.1.md` | di berkas skenario | dicek pemeriksa independen 2 putaran (`docs/scenarios/M0.1.pemeriksa.md`) / disetujui operator 2026-10-27 |
| M1.2 | Span recall, precision token, pengemasan anggaran, pemecahan gold per ayat dan Recall@K (H-048) | `docs/scenarios/M1.2.md` | di berkas skenario | dicek pemeriksa independen 2 putaran (`docs/scenarios/M1.2.pemeriksa.md`) / disetujui operator 2026-10-27 |
| M1.4 | Split berstrata dan pembulatan held-out (H-049), frontier, kebocoran held-out, pemecah seri sampai `setting_id` (H-034, H-055) | `docs/scenarios/M1.4.md` | di berkas skenario | dicek pemeriksa independen 2 putaran (`docs/scenarios/M1.4.pemeriksa.md`) / disetujui operator 2026-10-27 |
| M1.5 | Entity preservation, boundary coherence | `docs/scenarios/M1.5.md` | di berkas skenario | dicek pemeriksa independen 2 putaran (`docs/scenarios/M1.5.pemeriksa.md`) / disetujui operator 2026-10-27 |
| M2.1 | Transisi status usulan | | | |
| M2.3 | Verifier uji 1 dan 2, ambang fuzzy | | | |
| M2.4 | Uji 3 tiga nilai (stretch) | | | |
| M3.2 | Akuntansi token header dalam anggaran | | | |
| M4.3 | Round-trip profil | | | |

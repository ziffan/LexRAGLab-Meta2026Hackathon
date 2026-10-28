// Bentuk data dari backend (docs/DATA-CONTRACTS.md §2, §3, §4, §10; docs/API.md §2, §4).

export interface Span {
  start: number;
  end: number;
}

export interface AddressLevel {
  level: string;
  label: string;
}

export interface Chunk {
  chunk_id: string;
  doc_id: string;
  chunker_key: string;
  start: number;
  end: number;
  clean_sha256: string;
  section: string;
  address: string;
  address_levels: AddressLevel[];
  tokens_local: number;
  warnings: string[];
}

export interface Setting {
  setting_id: string;
  family: string;
  chunker: "structure_handwritten" | "structure_schema" | "fixed_size";
  chunk_size_tokens: number | null;
  overlap_tokens: number | null;
  schema_version: number | null;
  retrieval_mode: RetrievalMode;
  header_b: boolean;
  budget_tokens: number;
}

export type SplitName = "tune" | "held_out";
/** Kunci blok grid: UU PT `tune`/`held_out`; akta `all` (tanpa split, H-091). */
export type SplitKey = SplitName | "all";
export type RetrievalMode = "dense" | "bm25" | "hybrid";

export interface Item {
  id: string;
  split?: SplitName | null;
  family: string;
  query: string;
  doc_id: string;
  gold_spans: Span[];
  clean_sha256: string;
  mode: "literal" | "parafrase" | "tolak";
  origin: "operator" | "spark_disetujui";
  scene_checked?: boolean;
}

export interface CorpusDocInfo {
  doc_id: string;
  title: string;
  clean_sha256: string;
  char_count: number;
}

export interface Frac {
  covered: number;
  total: number;
}

/** GridPoint (DATA-CONTRACTS §10). `exact` memuat pecahan eksak sebagai string "a/b". */
export interface GridPoint {
  setting_id: string;
  split: SplitName | null;
  budget_tokens: number;
  mean_span_recall: number | null;
  mean_token_precision: number | null;
  mrr: number | null;
  mean_retrieved_tokens: number | null;
  fully_covered_count: Frac;
  dominated: boolean;
  /** Hanya akta (H-093): "no structure recognized" pada titik structure_handwritten; null untuk titik lain. */
  label?: string | null;
  /** Deret U2: true = header B on. Titik lama tanpa label dianggap off. */
  header_b?: boolean;
  n_gold: number;
  no_gold_count: number;
  exact: Record<string, string> | null;
}

export interface Frontier {
  split: SplitName | null;
  budget_tokens: number;
  point_ids: string[];
  grid_run_id: string;
}

export interface GridSplit {
  points: GridPoint[];
  frontier: Frontier | null;
}

export interface Skipped {
  setting_id: string;
  reason: string;
}

export interface QualityMetrics {
  setting_id: string;
  entity_preservation: number | null;
  boundary_coherence: number | null;
  recall_at_k: number | null;
  k: number;
}

export interface QualityCounts {
  entity_num: number;
  entity_den: number;
  bnd_num: number;
  bnd_den: number;
}

export interface QualityWithCounts extends QualityMetrics {
  counts?: QualityCounts;
  items_scope?: "all" | SplitName | "transfer";
  recall_n_items?: number;
}

export interface QualityComparison {
  budget_tokens: number;
  baseline_setting_id: string;
  selected_setting_id: string;
  baseline: QualityWithCounts;
  selected: QualityWithCounts;
}

/** RunRecord.failed_settings (DATA-CONTRACTS 12): setting header-on yang gagal; reason = kode (header_missing, ...). */
export interface FailedSetting {
  setting_id: string;
  reason: string;
  chunk_id: string | null;
}

/** Setting baris laporan transfer akta (H-091): structure_schema + mode/header/anggaran dari profil terbaik UU PT. */
export interface TransferSetting {
  setting_id: string;
  chunker: Setting["chunker"];
  schema_version: number | null;
  retrieval_mode: RetrievalMode;
  header_b: boolean;
  budget_tokens: number;
  source_setting_id: string;
  label: string;
}

export interface Grid {
  /** UU PT: tune + held_out. Akta: hanya `all` (H-091). */
  tune?: GridSplit;
  held_out?: GridSplit;
  all?: GridSplit;
  /** Akta: setting transfer (null bila UU PT belum punya pilihan atau tak ada padanan). */
  transfer?: TransferSetting | null;
  /** Akta: amplop ini ditandai final lewat config/akta_grid_final (banner "Pending operator review" hilang). */
  final?: boolean;
  selected: { setting_id: string } | null;
  quality_comparison: QualityComparison | null;
  skipped: Skipped[];
  failed_settings?: FailedSetting[];
  header_scope?: string | null;
  grid_run_id: string;
}

/** ItemMetrics (DATA-CONTRACTS §10) ditambah field bantu dari API. */
export interface ItemMetrics {
  item_id: string;
  setting_id: string;
  split: SplitName | null;
  gold_chars: number;
  covered_gold_chars: number;
  span_recall: number | null;
  retrieved_tokens: number;
  gold_tokens_retrieved: number;
  token_precision: number | null;
  reciprocal_rank: number | null;
  rank: number | null;
  recall_at_k: number | null;
  parts_hit: number;
  parts_total: number;
  fully_covered: boolean | null;
}

export interface ItemsSummary {
  n_items: number;
  by_origin: Record<string, number>;
  by_mode: Record<string, number>;
  by_split: Record<string, number> | null;
  control_in_held_out: number | null;
}

export interface Snapshot {
  family: string;
  budget_tokens: number;
  replay: boolean;
  config_hash: string;
  corpus: CorpusDocInfo[];
  items: Item[];
  items_summary: ItemsSummary;
  settings: Setting[];
  grid: Grid | null;
  metrics: ItemMetrics[];
  quality: QualityWithCounts[];
  // Bagian M2/M3 (docs/API.md 4). Opsional: snapshot lama tidak memuatnya.
  schemas?: SchemaRecord[];
  schema_diff?: SchemaDiff | null;
  schemas_rejected?: SchemaRejected[];
  header_b?: HeaderBView;
  /** Laporan per butir (build_report, H-077): held-out UU PT atau transfer akta; null bila belum ada grid (API.md section 4). */
  report?: Report | null;
}

export interface Retrieval {
  retrieved_chunk_ids: string[];
  ranks: number[];
  scores: number[];
  packed_tokens: number;
}

export interface DocResponse {
  doc_id: string;
  text: string;
  chunks: Chunk[] | null;
  headers: unknown[] | null;
}

export type Load<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; code: string; message: string }
  | { status: "ready"; data: T };

// ---- U3 (DATA-CONTRACTS §8, §12; API.md R1, W6) ----
export type AnswerStatus = "jawab" | "tolak" | "bukti_tidak_cukup";
export type Pass = "lulus" | "gagal";
export type ValidOnDate = "berlaku" | "dicabut" | "berlaku_bersyarat" | "tidak_dijalankan";

export interface Citation {
  alamat: string;
  teks: string;
}

export interface AnswerRecord {
  answer_id: string;
  item_id: string;
  setting_id: string;
  slot: "best" | "baseline";
  model_profile: string;
  context_chunk_ids: string[];
  budget_tokens: number;
  output: { status: AnswerStatus; jawaban: string | null; kutipan: Citation[] };
  flags: string[];
  run_id: string;
}

export interface VerifierResult {
  answer_id: string;
  citation_index: number;
  exists: Pass;
  faithful: Pass;
  faithful_score: number | null;
  valid_on_date: ValidOnDate;
  status_table_version: number | null;
  matched_chunk_id: string | null;
}

export interface RejectionSummary {
  setting_id: string;
  slot: "best" | "baseline";
  model_profile: string;
  answered_supported: number;
  answered_unsupported: number;
  abstained_correct: number;
  abstained_should_answer: number;
  n_items: number;
}

export type RunKind = "spark_a" | "spark_b" | "spark_c" | "spark_d" | "grid" | "measure";

export interface RunRecord {
  run_id: string;
  kind: RunKind;
  created_at: string;
  cache_key: string;
  config_hash: string;
  prompt_version: string | null;
  model: string | null;
  effort: string | null;
  usage_input_tokens: number | null;
  usage_cached_tokens: number | null;
  usage_output_tokens: number | null;
  cost_usd_micros: number | null;
  projected_cost_usd_micros: number | null;
  latency_ms: number;
  provider: string | null;
  quantization: string | null;
  status: "ok" | "error" | "cached" | "replay";
  error: { code: string; message: string } | null;
}

export interface AnswersResponse {
  best: AnswerRecord;
  baseline: AnswerRecord;
  verifier: VerifierResult[];
  summary: RejectionSummary[];
  runs: RunRecord[];
  /** UX-03: RunRecord panggilan asal (berbayar) untuk run `replay`/`cached`, dicocokkan lewat `cache_key`. Tidak ada di respons lama. */
  origin_runs?: RunRecord[];
}

export interface ModelProfileInfo {
  model_profile: string;
  model: string | null;
  available: boolean;
  /** Field di bawah dikirim R1 sejak M2.5; opsional supaya health.json statis lama tetap terbaca. */
  label?: string;
  provider?: string | null;
  quantization?: string | null;
  effort?: string | null;
  roles?: string[];
  local?: boolean;
  live_via_cli?: boolean;
  unavailable_reason?: string | null;
}

export interface Health {
  status: string;
  replay: boolean;
  model: string | null;
  config_hash: string;
  /** Jumlah `cost_usd_micros` seluruh RunRecord tersimpan (integer micro-USD); null/tidak ada = tidak terbaca. */
  run_cost_usd_micros?: number | null;
  /** Buku belanja `Ledger.spent` (`spend_micros` = cost + projected per record, H-063) atas SEMUA pool; jumlah U8. Bukan angka U0 sejak H-104. */
  ledger_spent_usd_micros?: number | null;
  /** H-104 butir 3: buku belanja pool default (hasil utama Contributor) = angka `Run cost (main results)` U0 dan README. */
  main_results_spent_usd_micros?: number | null;
  /** H-104 butir 3: belanja per pool (`default`, provider berplafon mis. `baseten`, `sweep`), urutan server. */
  pool_spend?: PoolSpend[] | null;
  /** Agregat per jenis run atas SEMUA RunRecord (server, tanpa limit R6); tabel per peran U8. */
  run_totals_by_kind?: RunTotal[] | null;
  model_profiles: ModelProfileInfo[];
}

/** R1 `pool_spend` (docs/API.md): integer micro-USD per pool. */
export interface PoolSpend {
  pool: string;
  spend_usd_micros: number;
}

/** R1 `run_totals_by_kind` (docs/API.md): integer; `spend_usd_micros` = buku belanja per jenis run. */
export interface RunTotal {
  kind: RunKind;
  runs: number;
  usage_input_tokens: number;
  usage_cached_tokens: number;
  usage_output_tokens: number;
  spend_usd_micros: number;
  unknown_runs: number;
}

// ---- U5 (DATA-CONTRACTS §6; API.md W9) ----
export interface SchemaLevel {
  order: number;
  name: string;
  marker_pattern: string;
  examples: string[];
  parent_order: number | null;
  is_chunk_unit: boolean;
}

export interface SchemaBody {
  family: string;
  levels: SchemaLevel[];
  default_chunk_level: number;
  notes: string | null;
}

export interface SchemaRecord {
  family: string;
  schema_version: number;
  source: "spark" | "operator";
  parent_version: number | null;
  body: SchemaBody;
  validation: { order: number; example: string; matched: boolean }[];
  run_id: string | null;
  created_at: string;
  operator_note: string | null;
  sample_checked?: boolean;
}

export interface SchemaDiffEntry {
  order: number | null;
  field: string;
  before: unknown;
  after: unknown;
}

export interface SchemaDiff {
  spark_version: number;
  operator_version: number;
  changed: SchemaDiffEntry[];
  boundary_diff: { doc_id: string; only_schema: unknown; only_handwritten: unknown }[];
}

export interface SchemaRejected {
  run_id: string;
  family: string;
  body: unknown;
  errors: string[];
  created_at: string;
}

// ---- U8 (DATA-CONTRACTS §7; runs/headers/projection) ----
export interface HeaderSample {
  chunk_id: string;
  granularity: "pasal" | "ayat" | "fixed_size";
  header: string;
  tokens_local: number;
  prompt_version: string | null;
  run_id: string | null;
}

export interface HeaderProjectionEntry {
  source: string;
  units: number;
  calls: number;
  cost_usd_micros: { expected: number; upper_cached: number; upper_no_cache: number };
  time: { estimated_seconds: number };
}

export interface HeaderBView {
  projection: { created_at: string; projections: Record<string, HeaderProjectionEntry> } | null;
  samples: HeaderSample[];
  stored_counts: Record<string, number>;
}

// ---- U7 (DATA-CONTRACTS 11; API.md W7, W8) ----
export interface HeldOutBlock {
  n_items: number;
  by_origin: Record<string, number>;
  mean_span_recall: number | null;
  mean_token_precision: number | null;
  fully_covered: { covered: number; total: number };
}

export interface Profile {
  profile_version: string;
  family: string;
  setting: Setting;
  schema: SchemaBody | null;
  corpus_hash: string;
  config_hash: string;
  chunk_set_hash: string;
  tokenizer: { name: string; version: string };
  clean_sha256: string;
  loader_rules_version: string;
  packing: string;
  embedder: { name: string; revision: string; max_seq_length: number } | null;
  held_out: HeldOutBlock | null;
  created_at: string;
}

/** W8 200. */
export interface ImportResult {
  ok: boolean;
  chunk_set_hash_matches: boolean;
}

export interface ReportCount {
  numerator: number;
  denominator: number;
  text: string;
}

export interface ReportRow {
  item_id: string;
  split: string;
  origin: string;
  mode: string;
  span_recall: ReportCount | null;
  token_precision: ReportCount | null;
  reciprocal_rank: number | null;
  recall_at_k: number | null;
  fully_covered: boolean | null;
  note: string | null;
}

export interface Report {
  family: string;
  title: string;
  /** Akta (H-091): setting yang dilaporkan, berlabel "transfer test, no profile selection". */
  setting?: TransferSetting;
  rows: ReportRow[];
  summary: { n_items: number; mean_span_recall: number | null; mean_token_precision: number | null; fully_covered: ReportCount };
  by_origin: Record<string, ReportGroup>;
  by_mode: Record<string, ReportGroup>;
}

/** Ringkasan satu asal/mode di `Report` (build_report `_groups`). */
export interface ReportGroup {
  n_items: number;
  n_gold: number;
  mean_span_recall: number | null;
  mean_token_precision: number | null;
}

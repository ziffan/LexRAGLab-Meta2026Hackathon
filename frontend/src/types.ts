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
export type RetrievalMode = "dense" | "bm25" | "hybrid";

export interface Item {
  id: string;
  split?: SplitName | null;
  family: string;
  query: string;
  doc_id: string;
  gold_spans: Span[];
  clean_sha256: string;
  mode: "literal" | "parafrase";
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

/** GridPoint (DATA-CONTRACTS �10). `exact` memuat pecahan eksak sebagai string "a/b". */
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
  items_scope?: "all" | SplitName;
  recall_n_items?: number;
}

export interface QualityComparison {
  budget_tokens: number;
  baseline_setting_id: string;
  selected_setting_id: string;
  baseline: QualityWithCounts;
  selected: QualityWithCounts;
}

export interface Grid {
  tune: GridSplit;
  held_out: GridSplit;
  selected: { setting_id: string } | null;
  quality_comparison: QualityComparison | null;
  skipped: Skipped[];
  grid_run_id: string;
}

/** ItemMetrics (DATA-CONTRACTS �10) ditambah field bantu dari API. */
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
}

export interface ModelProfileInfo {
  model_profile: string;
  model: string | null;
  available: boolean;
}

export interface Health {
  status: string;
  replay: boolean;
  model: string | null;
  config_hash: string;
  model_profiles: ModelProfileInfo[];
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

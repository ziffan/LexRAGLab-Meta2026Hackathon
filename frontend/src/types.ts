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

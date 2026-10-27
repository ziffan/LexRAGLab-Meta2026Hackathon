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
  retrieval_mode: string;
  header_b: boolean;
  budget_tokens: number;
}

export interface Item {
  id: string;
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

export interface Snapshot {
  family: string;
  budget_tokens: number;
  corpus: CorpusDocInfo[];
  items: Item[];
  settings: Setting[];
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

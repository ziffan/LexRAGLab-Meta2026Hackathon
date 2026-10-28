<!-- Tujuan: README publik repo app (bahasa Inggris, H-018): apa, kenapa, cara jalan, batas, disclaimer. -->
<!-- Sumber keputusan: H-002, H-004, H-005, H-006, H-007, H-013, H-014, H-016, H-017, H-018, H-028, H-029, H-031, H-032, H-039, H-041, H-043, H-044, H-045, H-047, H-048, H-051, H-053, H-054, H-060, H-078, H-086, H-089, H-090, H-091, H-093, H-098. -->

# LexRAGLab

Find the chunking and retrieval setting that feeds an LLM the right clauses of Indonesian legal documents, measured, not guessed.

Built for the Meta Global AI Developer Hackathon (Indie track, theme "Build for Your World") with Muse Spark (`muse-spark-1.3-contributor` through the Meta Model API).

> Research demo. Not legal advice.

## Theme: Build for Your World

The hackathon theme is "Bring Meta's models into your domain. Solve a problem you know firsthand, free up time and mental space, and make something possible that wasn't before." The domain here is Indonesian law.

- **A problem known firsthand.** The operator does agentic legal work (legal opinions, legal due diligence, contract drafting) in which the agent must consult a body of regulation that does not fit one context window (see [Why](#why)).
- **Time and mental space.** LexRAGLab aims to replace guessing a chunk size with a measured choice, and to keep the context an agent needs small. This is the hypothesis the evaluation tests, not a measured saving.
- **Something that wasn't possible before.** There is no public, standard benchmark for Indonesian legal RAG, so a retrieval setting for Indonesian legal text could not be chosen by measurement. Muse Spark reads a new document family, proposes its structure and evaluation items for operator review, and LexRAGLab scores every setting against the approved gold spans.

## What it is

LexRAGLab is an evaluation sandbox for chunking and retrieval on Indonesian legal text. For one family of documents with a homogeneous pattern, it searches a grid of settings (chunker, chunk size and overlap, dense / BM25 / hybrid retrieval, context header on or off) and reports which settings give the most gold evidence for a fixed token budget.

The output is a **versioned setting profile** you can export and reuse in your own RAG pipeline. An exported Company Law profile is in [`profiles/uupt/`](profiles/uupt/); loading it back rebuilds the same chunk set (checked by a hash) and is rejected if the corpus hash differs. The project stops at finding the setting; it is not a RAG product.

## Why

Legal RAG teams usually pick a chunk size by guess. In Indonesian regulation, a guess can cut an *ayat* (paragraph of an article) in half, and the model then cites half a rule. There is no public, standard benchmark for Indonesian legal RAG. LexRAGLab makes chunking a measurable design decision.

The motivation comes from practice, not from RAG as a trend. Agentic legal work (legal opinions, legal due diligence, contract drafting) has to consult a body of regulation (statutes and their implementing regulations) that does not fit in one agent context window. LexRAGLab aims to find settings that keep the context an agent needs small; that is a hypothesis the evaluation tests, not a measured saving.

The regulation and material figures below are the operator's measurements of prior engagements (not included in this repository). They are not outputs of this app, and nothing in LexRAGLab's results is derived from them.

- A single statute consulted for one legal opinion was about 320 thousand tokens, more than a 200-thousand-token window on its own.
- Of the regulation text, only about 10% was actually used.
- Whole material per job, composition not broken down into regulation versus other documents: about 1.2 million tokens for one transaction's legal opinion and about 5.8 million for a full due diligence file (1.2 to 5.8 times a 1-million-token window); about 2.2 million for contract drafting, or about 2.8 million with the clause library included.

Supporting, secondary: agent usage. These are the operator's measurements of prior engagements, from local agent transcripts at list API rates (computed from tokens, not billed amounts; not included in this repository). Legal due diligence (two engagements): about 15 billion cached input tokens re-read across about 120 agent sessions, roughly $8k. Legal opinion: about 800 million cached input tokens re-read across about 40 agent sessions, roughly $500. Contract drafting was not recorded; the operator estimates it to be similar to the legal opinion (an estimate, not a measurement). These describe the scale of agent usage, not an effect of this app.

## How "best" is defined

- Gold evidence is stored as **character spans** in the source document, so one item set can score any chunker. A gold span marks every *ayat* needed for the answer; it is split at *ayat* boundaries before Recall@K is computed.
- Settings are compared at a **fixed token budget**, not a fixed K. Tokens are counted with one local tokenizer for every setting.
- Main metrics: **span recall** and **token precision**. Also reported: MRR, Recall@K, entity preservation, boundary coherence.
- Results are shown as a **Pareto frontier** (recall vs tokens). Settings are chosen on a tune split and reported on a held-out split, per item, with raw counts and no significance claims.

## What Muse Spark does

| Role | What `muse-spark-1.3-contributor` does |
|---|---|
| A. Structure induction | Reads sample documents of a new family and proposes a flat hierarchy schema that drives a deterministic chunker. The operator corrects it; both versions are kept |
| B. Contextual chunking | Writes a context header for each chunk with the source document cached. Header on/off is a grid axis, and header tokens count against the budget |
| C. End-to-end check | Answers an item from the best profile and from a baseline profile, with citations. A deterministic verifier (not an LLM) checks that each citation exists and is faithful to the source |
| D. Item proposals | Proposes (query, gold span) pairs in literal and paraphrase modes. The operator reviews every proposal; only approved items are used |

The grid search itself uses no LLM. All Model API calls use the Responses API with strict structured output.

Role C comparators (secondary, role C only): the same answer step can be re-run for the best and baseline profiles with two open-weight models, selectable in the evidence panel. **Muse Spark Open** runs on a hosted Baseten endpoint (`meta-models/muse-spark-open-1026`, Responses API, strict structured output). **Muse Glimmer** (`meta/muse-glimmer`, Q4_K_M, `reasoning_effort` high) runs locally on the operator's machine through an OpenAI-compatible loopback endpoint, with client-side schema validation; this is an open-weight model running on the operator's hardware, not Muse Spark weights. Each comparator's runs are stored and labelled separately and are never mixed with `muse-spark-1.3-contributor` runs. Stored runs exist for the three demo items only (see Limits); no general claim is made about either model's Indonesian-language quality.

## Document families

| Family | Scope |
|---|---|
| Indonesian Company Law (UU 40/2007), an unofficial consolidation prepared by the operator from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022, with notes on which later law or decision changed each provision | Full: grid and roles A, B, C, D; settings chosen on tune, reported on held-out |
| Notarial deeds | Transfer: **five synthetic deeds of establishment**, written by an AI agent and reviewed by the operator, with fictitious identities. Shows role A on a family with no existing parser: the deed structure schema is version 2, corrected by the operator from the Spark proposal (version 1). The deed items are not split into tune and held-out; the best Company Law setting (dense retrieval, header off, 2,000-token budget) is applied to the deed schema and reported per item as a transfer test, with no profile selection. Results: see "Deed results (transfer test)" below |
| Internal policies | Mentioned as the next family; no documents included |

## Evaluation items

Current count, from `data/butir/` (`uupt.v13.jsonl`, `akta.v85.jsonl`):

| Family | Items | Origin | Notes |
|---|---|---|---|
| Company Law | **20** | 9 operator-written control items (`origin: operator`); 11 Spark-proposed items approved by the operator (`origin: spark_disetujui`; 5 approved as proposed, 6 edited by the operator) | 1 must-refuse item with no gold span. Tune / held-out split: 11 / 9 |
| Notarial deeds (synthetic) | **84** | all Spark-proposed, approved by the operator (82 as proposed, 2 edited); none operator-written | 43 literal, 26 paraphrase, 15 must-refuse (3 per deed, no gold span); the 69 gold items are spread over the five deeds (12 to 16 each). No tune / held-out split; transfer test only |

Operator-written control items detect circularity between Spark-proposed queries and their spans. There are none for deeds, so that check does not apply to the deed numbers. Two Company Law proposals were rejected and are not counted (`runs/proposals/records/`). The Company Law count may still change after the operator's final review.

## Deed results (transfer test)

Source: the stored deed grid run (`runs/grid/86e701f5…`, key `86e701f5…`), item file `data/butir/akta.v85.jsonl`, deed structure schema version 2 (`runs/schemas/akta/v2.json`, `source: operator`). The grid has 36 settings: 3 chunkers (unstructured, fixed-size 512 tokens with 64 overlap, deed structure schema) x 3 retrieval modes (dense, BM25, hybrid) x context header on / off x 2 token budgets (1,000 and 2,000); 29 of them were evaluated, because the header-on twin is run only for settings on the frontier (`frontier_only` scope). All 84 items are scored together; there is no split and no setting is selected on them (marked "transfer test, no profile selection"). The 15 must-refuse items have no gold span, so they have no recall and are left out of the means below. The numbers are the 69 gold items at the 2,000-token budget:

| Chunker | Retrieval | Header | Items fully covered | Mean span recall | MRR |
|---|---|---|---|---|---|
| unstructured, `structure_handwritten` (one chunk per deed) | any of the three | on / off | 0 of 69 | 0.000 | 0.000 |
| fixed-size 512 / 64 | dense | off | 64 of 69 | 0.937 | 0.773 |
| fixed-size 512 / 64 | hybrid | off | 62 of 69 | 0.899 | 0.731 |
| fixed-size 512 / 64 | BM25 | off | 57 of 69 | 0.826 | 0.655 |
| deed structure schema v2 | dense | off | 69 of 69 | 1.000 | 0.955 |
| deed structure schema v2 | dense | on | 69 of 69 | 1.000 | 0.949 |
| deed structure schema v2 | hybrid | off | 68 of 69 | 0.986 | 0.801 |
| deed structure schema v2 | hybrid | on | 67 of 69 | 0.971 | 0.814 |
| deed structure schema v2 | BM25 | off | 62 of 69 | 0.899 | 0.675 |

- The **transfer setting** is the best Company Law setting applied to the deeds: structure-schema chunker, dense retrieval, header off. It fully covers 69 of 69 gold items with a mean token precision of 0.0252 (2.5%); the stored grid marks it dominated by the header-on dense point, which covers the same items with fewer retrieved tokens (1,889 vs 1,904 on average). Header-on variants exist only for some points (header scope: frontier only), so the table has no BM25 header-on row and no fixed-size header-on row.
- The **unstructured** point is labelled "no structure recognized": the Company Law parser finds no structure in a deed and returns one chunk per deed, larger than the budget, so it scores zero under the token budget. Its Recall@5 nevertheless reads 1.000 (one chunk per deed), so Recall@K alone says nothing about token-budget coverage and cannot be compared across chunkers.
- Deed **Recall@K is not comparable with Company Law Recall@K**. It is computed at the default chunk level of the deed schema (`recall_unit: default_chunk_level`). Compare chunkers within the deed family only.
- Small n: 69 gold items from five documents, all proposed by Spark and approved by the operator. The table gives raw counts. It claims no significance, and it does not show that the structure schema beats the baselines in general.

## Run it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js with npm. Copy `.env.example` to `.env` and fill the values locally; `.env` is git-ignored and never committed. Replay needs no key.

```bash
uv sync                                   # backend dependencies
uv run python -m backend.api              # backend, bound to 127.0.0.1:8000 only
cd frontend && npm install && npm run dev # frontend dev server on 127.0.0.1:5173, proxies /api to the backend
```

Static replay export (no backend, no model calls):

```bash
uv run python -m backend.replay.export --out dist-static   # writes dist-static/data from stored runs
cd frontend && npm run build:static                        # builds the static UI into dist-static/
uv run python -m backend.replay.export --check dist-static # scan the snapshot for keys, local paths, hosts
```

Open `dist-static/index.html` through any static file server, or use the published page below.

```text
backend:   Python 3.12 + FastAPI
frontend:  React + TypeScript + Vite
model:     muse-spark-1.3-contributor, Responses API (model ID in config/model)
storage:   files only (no database, no vector database)
```

A replay mode serves every screen from stored runs (`runs/`) and the document and item data (`data/`) without calling the Model API.

Live version: TODO(operator): GitHub Pages link, added after the repository is public. The web version is a **replay**: a static export of stored runs with no backend, no API key, and no model calls.

## Limits

- Small item sets (n is small; see the count above); results are per item with raw counts, without significance claims.
- The pre-event consolidation covers one statute only, as of 30 December 2022; later amendments are not reflected.
- Comparators (Muse Spark Open on Baseten, Muse Glimmer locally) cover role C only, and only three demo items (`kontrol-K-09`, `kontrol-K-01`, `kontrol-K-08`), each with the best and the baseline profile: 6 stored runs per comparator (`runs/spark/records/`). That is a smoke-level check, not a quality comparison, and no comparator quality figure is claimed. The Spark Open runs cost 30,591 micro-USD in total; the local Glimmer runs cost 0. Any open-weight bonus claim waits for the organizers' confirmation of how own-hardware use is verified.
- Deed results rest on five synthetic documents and 69 gold items (plus 15 must-refuse items with no retrieval score). Deeds have no operator-written control items and no held-out split, and the transfer test selects nothing.
- Model API spend recorded in the stored runs (`runs/spark/records/`, summed by the budget ledger): 585,376 micro-USD in total (about 0.59 USD): 554,785 on `muse-spark-1.3-contributor` (Meta API), 30,591 on Muse Spark Open (Baseten), 0 on local Muse Glimmer. Cost comes from the `usage` of each call.
- Token counts use a local tokenizer calibrated once against the API token-count endpoint; billed tokens may differ.
- The "valid on date" citation check is a stretch goal and may be absent.
- Indonesian legal text is shown in Indonesian, with short English glosses where needed.

## Data and licensing

- The Company Law text is an unofficial consolidation of UU 40/2007 prepared by the operator before the hackathon from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022 (Perppu 2/2022, enacted as law by UU 6/2023). A source list names each amending law and Constitutional Court decision. Regulation texts and court decisions are public legal texts.
- No real deeds, client data, or internal documents are included. The five synthetic deeds were written by an AI agent and reviewed by the operator. All names, companies, notaries, and addresses in them are fictitious; any resemblance to real persons or entities is coincidental.
- Model API calls use `muse-spark-1.3-contributor` (Contributor mode: Meta may use the content to train future models). This is acceptable here because every document is public or synthetic. For confidential document families, set the Standard model ID in `config/model`.
- License: Apache-2.0 for everything this project created: code, configuration, prompts, documentation, and the five synthetic deeds (see `LICENSE`). Third-party attributions are in `NOTICE`; the IBM Plex font license texts (SIL OFL 1.1) are in `licenses/`. Regulation texts are reproduced as public legal texts (UU 28/2014 Article 42) with sources cited and are not relicensed. The Muse Spark Open tokenizer is not included; it is read from the user's local Hugging Face cache and is downloaded from its official source under its own license (Muse Model License). Muse Glimmer weights, if used, are not included; attribution follows its model card. Frontend runtime dependencies are MIT, ISC, or BSD-3-Clause (table in `docs/SECURITY-COMPLIANCE.md` section 4).

**Built with Muse Spark Open.** Token counts use the Muse Spark Open tokenizer (revision pinned in `config/tokenizer.toml`; `o200k_base` is the fallback).

### Corpus sources (Company Law, unofficial consolidation)

The consolidation is not an official text (not a State Gazette / LN-BN copy); for official citation refer to LN 2007 No. 106 / TLN No. 4756. It is built on UU 40/2007 and incorporates:

- Perppu No. 2 of 2022, enacted as law by UU No. 6 of 2023 (in force 30 December 2022): amends Article 1, 7, 32, 153 and inserts Articles 153A to 153J.
- UU No. 24 of 2011 (in force 25 November 2011), see the footnote in the file.
- Constitutional Court Decision No. 84/PUU-XI/2013 (read 9 October 2014), see the footnote in the file.

Source: `data/uupt/UU_40_2007_PERSEROAN_TERBATAS.md` (frontmatter lists these sources). Regulation texts and court decisions are not protected by copyright (UU 28/2014, Article 42).

## Built before vs during the hackathon

The hackathon started on 26 Oct 2026, 23:00 WIB. The first commit in this repository is dated 26 Oct 2026 23:23 WIB, after kickoff. Only two things in this repository were prepared before that (drafted 25-26 Oct, committed afterwards, each in a separately labelled commit).

| Built before kickoff (25–26 Oct 2026) | Built during the hackathon |
|---|---|
| The planning specs in [`docs/`](docs/), imported in one labelled commit (`docs: import pre-event planning`). Planning only: no code. No pre-event prototype code is copied into this repository | All code, configuration, prompts, evaluation items, synthetic deeds, stored runs, profiles, and the live replay |
| The Company Law file: an unofficial consolidation of UU 40/2007, consolidated as of 30 December 2022, prepared by the operator from the regulation texts and Constitutional Court decisions; committed separately as pre-event material (`data: add UU 40/2007 consolidated text`) | Every change to the specs after the import commit |

The visual theme of the UI (colour tokens, IBM Plex typography, component patterns) comes from the operator's pre-event design mockup (H-083, H-044); the mockup markup is not copied and the layout follows `docs/UI-SPEC.md`.

The five synthetic deeds are written during the hackathon by an AI agent (the development agent) and reviewed by the operator. All identities in them are fictitious.

## Disclaimer

Research demo. Not legal advice. Do not rely on any output for legal decisions.

## Documentation

Specs live in [`docs/`](docs/): [PRD](docs/PRD.md), [UI-SPEC](docs/UI-SPEC.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [DATA-CONTRACTS](docs/DATA-CONTRACTS.md), [API](docs/API.md), [EVAL-SPEC](docs/EVAL-SPEC.md), [SPARK-ROLES](docs/SPARK-ROLES.md), [SECURITY-COMPLIANCE](docs/SECURITY-COMPLIANCE.md), [MILESTONES](docs/MILESTONES.md), [DECISIONS](docs/DECISIONS.md), [VIDEO](docs/VIDEO.md). Spec documents are written in Indonesian.

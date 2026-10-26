<!-- Tujuan: README publik repo app (bahasa Inggris, H-018): apa, kenapa, cara jalan, batas, disclaimer. -->
<!-- Sumber keputusan: H-002, H-004, H-005, H-006, H-007, H-013, H-014, H-016, H-017, H-018, H-028, H-029, H-031, H-032, H-039, H-041, H-043, H-044, H-045, H-047, H-048, H-051, H-053, H-054. -->

# LexRAGLab

Find the chunking and retrieval setting that feeds an LLM the right clauses of Indonesian legal documents, measured, not guessed.

Built for the Meta Global AI Developer Hackathon (Indie track) with `muse-spark-1.3`.

> Research demo. Not legal advice.

## What it is

LexRAGLab is an evaluation sandbox for chunking and retrieval on Indonesian legal text. For one family of documents with a homogeneous pattern, it searches a grid of settings (chunker, chunk size and overlap, dense / BM25 / hybrid retrieval, context header on or off) and reports which settings give the most gold evidence for a fixed token budget.

The output is a **versioned setting profile** you can export and reuse in your own RAG pipeline. The project stops at finding the setting; it is not a RAG product.

## Why

Legal RAG teams usually pick a chunk size by guess. In Indonesian regulation, a guess can cut an *ayat* (paragraph of an article) in half, and the model then cites half a rule. There is no public, standard benchmark for Indonesian legal RAG. LexRAGLab makes chunking a measurable design decision.

## How "best" is defined

- Gold evidence is stored as **character spans** in the source document, so one item set can score any chunker. A gold span marks every *ayat* needed for the answer; it is split at *ayat* boundaries before Recall@K is computed.
- Settings are compared at a **fixed token budget**, not a fixed K. Tokens are counted with one local tokenizer for every setting.
- Main metrics: **span recall** and **token precision**. Also reported: MRR, Recall@K, entity preservation, boundary coherence.
- Results are shown as a **Pareto frontier** (recall vs tokens). Settings are chosen on a tune split and reported on a held-out split, per item, with raw counts and no significance claims.

## What Muse Spark does

| Role | What `muse-spark-1.3` does |
|---|---|
| A. Structure induction | Reads sample documents of a new family and proposes a flat hierarchy schema that drives a deterministic chunker. The operator corrects it; both versions are kept |
| B. Contextual chunking | Writes a context header for each chunk with the source document cached. Header on/off is a grid axis, and header tokens count against the budget |
| C. End-to-end check | Answers an item from the best profile and from a baseline profile, with citations. A deterministic verifier (not an LLM) checks that each citation exists and is faithful to the source |
| D. Item proposals | Proposes (query, gold span) pairs in literal and paraphrase modes. The operator reviews every proposal; only approved items are used |

The grid search itself uses no LLM. All Model API calls use the Responses API with strict structured output.

Optional on-prem comparison (stretch): role C can be re-run for the best and baseline profiles with **Muse Glimmer** (open-weight) running locally on the operator's machine, selectable in the evidence panel. Glimmer runs are stored and labelled separately and are never mixed with `muse-spark-1.3-contributor` runs. Glimmer is not the same weights as Muse Spark, and no general claim is made about its Indonesian-language quality.

## Document families

| Family | Scope |
|---|---|
| Indonesian Company Law (UU 40/2007), an unofficial consolidation prepared by the operator from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022, with notes on which later law or decision changed each provision | Full: grid and roles A, B, C, D; settings chosen on tune, reported on held-out |
| Notarial deeds | Transfer: **five synthetic deeds of establishment**, written by an AI agent and reviewed by the operator, with fictitious identities. Shows role A on a family with no existing parser. The deed items are not split into tune and held-out; the best Company Law profile is tested on them and reported per item as a transfer test |
| Internal policies | Mentioned as the next family; no documents included |

## Evaluation items

`{n} items: {a} operator-written, {b} Spark-proposed and operator-approved` — filled in from the final run. Operator-written control items detect circularity between Spark-proposed queries and their spans.

## Run it

[placeholder — filled in at M5]

```text
backend:   Python 3.12 + FastAPI
frontend:  React + TypeScript + Vite
model:     muse-spark-1.3-contributor, Responses API (model ID in config/model)
storage:   files only (no database, no vector database)
```

A replay mode serves every screen from stored runs (`runs/`) and the document and item data (`data/`) without calling the Model API.

Live version: [placeholder — GitHub Pages link, filled in at M5]. It is a static export of the replay mode: no backend, no API key, no model calls.

## Limits

- Small item sets; results are per item with raw counts, without significance claims.
- Token counts use a local tokenizer calibrated once against the API token-count endpoint; billed tokens may differ.
- The "valid on date" citation check is a stretch goal and may be absent.
- Indonesian legal text is shown in Indonesian, with short English glosses where needed.

## Data and licensing

- The Company Law text is an unofficial consolidation of UU 40/2007 prepared by the operator before the hackathon from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022 (Perppu 2/2022, enacted as law by UU 6/2023). A source list names each amending law and Constitutional Court decision. Regulation texts and court decisions are public legal texts.
- No real deeds, client data, or internal documents are included. The five synthetic deeds were written by an AI agent and reviewed by the operator. All names, companies, notaries, and addresses in them are fictitious; any resemblance to real persons or entities is coincidental.
- Model API calls use `muse-spark-1.3-contributor` (Contributor mode: Meta may use the content to train future models). This is acceptable here because every document is public or synthetic. For confidential document families, set the Standard model ID in `config/model`.
- License: Apache-2.0 for code, configuration, prompts, and documentation in this repository. Regulation texts are reproduced as public legal texts with sources cited and are not relicensed. The Muse Spark Open tokenizer is not included; download it from its official source under its own license. Muse Glimmer weights, if used, are not included; attribution follows its model card.

## Built before vs during the hackathon

The hackathon started on 26 Oct 2026, 23:00 WIB. Only two things in this repository were prepared before that.

| Built before kickoff (25–26 Oct 2026) | Built during the hackathon |
|---|---|
| The planning specs in [`docs/`](docs/), imported in one labelled commit. Planning only: no code | All code, configuration, prompts, evaluation items, synthetic deeds, stored runs, profiles, and the live replay |
| The Company Law file: an unofficial consolidation of UU 40/2007, consolidated as of 30 December 2022, prepared by the operator from the regulation texts and Constitutional Court decisions; committed separately as pre-event material | Every change to the specs after the import commit |

The five synthetic deeds are written during the hackathon by an AI agent (the development agent) and reviewed by the operator. All identities in them are fictitious.

## Disclaimer

Research demo. Not legal advice. Do not rely on any output for legal decisions.

## Documentation

Specs live in [`docs/`](docs/): [PRD](docs/PRD.md), [UI-SPEC](docs/UI-SPEC.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [DATA-CONTRACTS](docs/DATA-CONTRACTS.md), [API](docs/API.md), [EVAL-SPEC](docs/EVAL-SPEC.md), [SPARK-ROLES](docs/SPARK-ROLES.md), [SECURITY-COMPLIANCE](docs/SECURITY-COMPLIANCE.md), [MILESTONES](docs/MILESTONES.md), [DECISIONS](docs/DECISIONS.md), [VIDEO](docs/VIDEO.md). Spec documents are written in Indonesian.

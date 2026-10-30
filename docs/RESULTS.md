# Results detail

Purpose: full tables, notes, and run sources for the results summarised in the README.
Moved from README.md; the README keeps a summary.

All numbers come from stored runs under [`../runs/`](../runs/). Nothing here is a new measurement.

## Evaluation items

Current count, from `data/butir/` (`uupt.v16.jsonl`, `akta.v85.jsonl`). Enum values in the item files are Indonesian: `spark_disetujui` = Spark-proposed, approved by the operator; `tolak` = refuse (the answer is not in the source); `kontrol-K-..` = operator control item IDs.

| Family | Items | Origin | Notes |
|---|---|---|---|
| Company Law | **23** | 9 operator-written control items (`origin: operator`); 14 Spark-proposed items approved by the operator (`origin: spark_disetujui`; 8 approved as proposed, 6 edited by the operator) | 3 must-refuse items (`mode: tolak`, answer not in the statute) plus 1 operator control item with no gold span. Tune / held-out split: 13 / 10 (1 must-refuse item held out) |
| Notarial deeds (synthetic) | **84** | all Spark-proposed, approved by the operator (82 as proposed, 2 edited); none operator-written | 43 literal, 26 paraphrase, 15 must-refuse (3 per deed, no gold span); the 69 gold items are spread over the five deeds (12 to 16 each). No tune / held-out split; transfer test only |

Operator-written control items detect circularity between Spark-proposed queries and their spans. There are none for deeds, so that check does not apply to the deed numbers. Two Company Law proposals were rejected and are not counted (`../runs/proposals/records/`).

## Document families

| Family | Scope |
|---|---|
| Indonesian Company Law (UU 40/2007), an unofficial consolidation prepared by the operator from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022, with notes on which later law or decision changed each provision | Full: grid and roles A, B, C, D; settings chosen on tune, reported on held-out |
| Notarial deeds | Transfer: **five synthetic deeds of establishment**, written by an AI agent and reviewed by the operator, with fictitious identities. Shows role A on a family with no existing parser: the deed structure schema is version 2, corrected by the operator from the Spark proposal (version 1). The deed items are not split into tune and held-out; the best Company Law setting (dense retrieval, header off, 2,000-token budget) is applied to the deed schema and reported per item as a transfer test, with no profile selection. Results: see "Deed results (transfer test)" below |
| Internal policies | Mentioned as the next family; no documents included |

## Company Law (selected setting)

Selected setting: structure-schema chunker (schema v2), dense retrieval, header off, 2,000-token budget. Held-out (10 items; 4 operator-written, 6 Spark-proposed and approved): 6 of the 8 items that have a gold span fully covered, mean span recall 0.75, mean token precision 0.0218; raw counts, no significance claim. Source: the exported profile [`../profiles/uupt/d7a9dd244260e256789d10d02bd50b1f125bcd1b8a088f2a8058c2f222c58ebf.json`](../profiles/uupt/d7a9dd244260e256789d10d02bd50b1f125bcd1b8a088f2a8058c2f222c58ebf.json) (field `held_out`); held-out results are also shown on the report screen of the app.

## Deed results (transfer test)

Source: the stored deed grid run ([`../runs/grid/86e701f56a3bc5f83268b4cf8590d9dfe641773b8234b3e826c4c4db2b517c2e.json`](../runs/grid/86e701f56a3bc5f83268b4cf8590d9dfe641773b8234b3e826c4c4db2b517c2e.json), key `86e701f5…`), item file `data/butir/akta.v85.jsonl`, deed structure schema version 2 (`runs/schemas/akta/v2.json`, `source: operator`). The grid has 36 settings: 3 chunkers (unstructured, fixed-size 512 tokens with 64 overlap, deed structure schema) x 3 retrieval modes (dense, BM25, hybrid) x context header on / off x 2 token budgets (1,000 and 2,000); 29 of them were evaluated, because the header-on twin is run only for settings on the frontier (`frontier_only` scope). All 84 items are scored together; there is no split and no setting is selected on them (marked "transfer test, no profile selection"). The 15 must-refuse items have no gold span, so they have no recall and are left out of the means below. The numbers are the 69 gold items at the 2,000-token budget:

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

Back to the [README](../README.md).

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

Selected setting: structure-schema chunker (schema v2), dense retrieval, header off, 2,000-token budget. Held-out (10 items; 4 operator-written, 6 Spark-proposed and approved): 6 of the 8 items that have a gold span fully covered, mean span recall 0.75, mean token precision 0.0218; raw counts, no significance claim. Source: the exported profile [`../profiles/uupt/d7a9dd244260e256789d10d02bd50b1f125bcd1b8a088f2a8058c2f222c58ebf.json`](../profiles/uupt/d7a9dd244260e256789d10d02bd50b1f125bcd1b8a088f2a8058c2f222c58ebf.json) (field `held_out`); held-out results are also shown on the report screen of the app. The two misses are both paraphrase items and fail for different reasons. `kontrol-K-07` (operator-written, "dismissal of a commissioner") is a retrieval miss: its gold span is Article 119, a one-sentence cross-reference ("Article 105 applies mutatis mutandis"), and none of the top 5 chunks contain it (Recall@5 = 0); the context holds the longer neighbouring articles on commissioners and directors instead. `usulan-dbd56534fe41df4e` (Spark-proposed, on the social and environmental responsibility duty in Article 74) is a budget miss: the gold chunk is in the top 5 (Recall@5 = 1), but the two higher-ranked structure chunks, Article 1 (definitions) and the General Elucidation (Penjelasan Umum), fill 1,941 of the 2,000 tokens, so it is never packed. Source: stored retrieval for the selected setting (`d7a9dd24…`, endpoint R5) and the per-item rows of the held-out report.

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

## Reasoning effort sweep (comparison runs)

The sweep re-ran roles A, B, and C at other `reasoning_effort` levels for Muse Spark (Contributor), Muse Spark Open (Baseten), and Muse Glimmer (local). These are separate runs; the main results, profiles, and grid stay on Contributor at `low`. Which levels ran, partial role B coverage, and spend per pool are in [LIMITS.md](LIMITS.md#effort-sweep).

Sources: call statistics from `runs/spark/records/`; role A schemas from `runs/schemas/<family>/compare/<profile>/`; role B stores and grids from `runs/headers_compare/` and `runs/grid_compare/<profile>/`; role C cells from `runs/compare_report/c/sweep_*.json`. Output tokens include reasoning tokens (billed as output); the stored records do not split reasoning out. Latency is the median wall-clock time per call. Call counts differ between rows because the runs cover different stores, so compare the per-call columns, not the totals. Small n, no significance test, and no general claim about any model's quality.

Run labels: **main** = main results; **comparator** = the base comparator run (Spark Open at `low`, Glimmer at `high`); **sweep** = the effort sweep.

### Role B (context header per chunk)

| Model | Effort | Run | Calls | Rejected (header over 40 tokens) | Mean output tokens per call | Median latency (ms) | Cost (micro-USD) |
|---|---|---|---|---|---|---|---|
| Contributor | `low` | main | 1,926 | 7.4% | 566 | 6,038 | 526,265 |
| Contributor | `medium` | sweep | 1,048 | 10.5% | 978 | 9,885 | 400,056 |
| Contributor | `high` | sweep | 1,066 | 11.4% | 1,174 | 11,338 | 477,669 |
| Contributor | `xhigh` | sweep | 1,068 | 10.8% | 1,913 | 16,698 | 660,432 |
| Spark Open | `low` | comparator | 1,783 | 45.8% | 462 | 3,588 | 15,366,732 |
| Spark Open | `medium` | sweep | 2,923 | 65.7% | 862 | 4,881 | 30,688,764 |
| Glimmer | `low` | sweep | 543 | 14.5% | 259 | 11,520 | 0 (local) |
| Glimmer | `medium` | sweep | 534 | 14.4% | 498 | 21,875 | 0 (local) |

Comparator grids are stored in `runs/grid_compare/<profile>/` for each row of this table except Contributor `low` (main grid in `runs/grid/`); Glimmer at `high` has no role B run and no grid. Header coverage is partial for several profiles, so the number of header-on Company Law grid points differs between profiles (from 1 to 9), and recall is not compared across effort levels here.

### Role A (structure schema proposal)

"Differences vs operator v2" counts the levels and fields in which the comparator schema differs from the operator-corrected schema (`v2.json`), for Company Law / deeds. It describes distance, not quality; no comparator schema is ever made active.

| Model | Effort | Run | Calls (valid) | Mean output tokens per call | Median latency (ms) | Cost (micro-USD) | Differences vs operator v2 (Company Law / deeds) |
|---|---|---|---|---|---|---|---|
| Contributor | `low` | main | 2 (2) | 4,034 | 40,312 | 8,170 | v2 is the operator's correction of this proposal |
| Contributor | `medium` | sweep | 2 (2) | 6,032 | 56,295 | 8,969 | 14 / 14 |
| Contributor | `high` | sweep | 6 (2; 4 incomplete) | 8,911 | 77,545 | 17,538 | 20 / 14 |
| Contributor | `xhigh` | sweep | 7 (2; 4 incomplete, 1 timeout) | 9,574 | 82,954 | 45,897 | 14 / 14 |
| Spark Open | `low` | comparator | 2 (2) | 1,481 | 9,127 | 93,751 | 12 / 5 |
| Spark Open | `medium` | sweep | 3 (1; 2 rejected) | 3,263 | 18,586 | 130,038 | no valid schema / 6 |
| Spark Open | `high` | sweep | 2 (2) | 6,165 | 25,703 | 133,565 | 13 / 6 |
| Spark Open | `xhigh` | sweep | 2 (2) | 13,004 | 50,530 | 191,693 | 14 / 7 |
| Glimmer | `low` | sweep | 2 (2) | 1,035 | 63,208 | 0 (local) | 15 / 13 |
| Glimmer | `medium` | sweep | 3 (2; 1 rejected) | 3,470 | 138,823 | 0 (local) | 14 / 15 |
| Glimmer | `high` | comparator | 5 (2; 2 invalid requests, 1 rejected) | 7,648 | 303,415 | 0 (local) | 14 / 15 |

### Role C (cited answer), three demo items

Items `kontrol-K-09`, `kontrol-K-01`, `kontrol-K-08`, each answered with the best and the baseline Company Law setting. Cells are supported / unsupported / abstained correctly / abstained but should have answered.

| Model | Effort | Run | Best setting | Baseline setting |
|---|---|---|---|---|
| Contributor | `low` | main | 2 / 0 / 1 / 0 | 0 / 0 / 2 / 1 |
| Contributor | `medium`, `high`, `xhigh` | sweep | 2 / 0 / 1 / 0 | 0 / 0 / 2 / 1 |
| Spark Open | `low` | comparator | 1 / 1 / 1 / 0 | 1 / 0 / 2 / 0 |
| Spark Open | `medium`, `high`, `xhigh` | sweep | 2 / 0 / 1 / 0 | 0 / 0 / 2 / 1 |
| Glimmer | `low`, `medium` | sweep | 2 / 0 / 1 / 0 | 0 / 0 / 2 / 1 |
| Glimmer | `high` | comparator | 2 / 0 / 1 / 0 | 0 / 0 / 2 / 1 |

The sweep rows come from the stored reports. The main and comparator rows have no stored report file; they were graded offline from the stored answers in `runs/answers/` with the same deterministic verifier (`backend.answer.compare_c.grade_cells`, no model call); run over the stored sweep answers, the same function reproduces all eight stored sweep reports exactly. Mean output tokens per role C call: Contributor 470, 725, 817, 1,503 (`low` to `xhigh`); Spark Open 219, 654, 1,416, 1,372 (`xhigh` slightly below `high`); Glimmer 260, 458, 851 (`low` to `high`). The Contributor `low`, Spark Open `low`, and Glimmer `high` figures also include the must-refuse items.

### What the sweep shows

- On the three demo items, every sweep level of every model gives the same role C cells as Contributor at `low`. The only differing row is the Spark Open `low` comparator run (one unsupported answer with the best setting, one supported answer with the baseline). Three items cannot show an effect of effort either way.
- Higher effort costs more output tokens and time for every model and role, with one exception: Spark Open role C at `xhigh` is slightly below `high` (mean output 1,372 vs 1,416 tokens, median latency 5,056 ms vs 5,182 ms). For Contributor role B, mean output per call grows from 566 to 1,913 tokens and median latency from 6,038 ms to 16,698 ms (`low` to `xhigh`), while the header rejection rate stays between 7.4% and 11.4%.
- Spark Open role B rejects far more headers than the other two models, and more at `medium` than at `low` (45.8% to 65.7%), and its role B spend is the largest in the sweep. This is consistent with retries: each retry sends the document prefix again (see G-45 in [GOTCHAS.md](GOTCHAS.md)).
- At `high` and `xhigh`, Contributor role A returned incomplete responses on several attempts before producing a valid schema.
- The main results were run at `low` before the sweep; this data gives no reason to change that.

Back to the [README](../README.md).

# Limits, comparators, effort sweep, and cost

Purpose: full limits and run-cost detail behind the short Limits list in the README.
Moved from README.md; the README keeps a summary.

## General limits

- Small item sets (n is small; see the count in [RESULTS.md](RESULTS.md)); results are per item with raw counts, without significance claims.
- The pre-event consolidation covers one statute only, as of 30 December 2022; later amendments are not reflected.
- Deed results rest on five synthetic documents and 69 gold items (plus 15 must-refuse items with no retrieval score). Deeds have no operator-written control items and no held-out split, and the transfer test selects nothing.
- Token counts use a local tokenizer calibrated once against the API token-count endpoint; billed tokens may differ.
- The "valid on date" citation check is a stretch goal and may be absent.
- Indonesian legal text is shown in Indonesian, with short English glosses where needed.
- The answer panel (U3) follows the setting chosen in the chunk view (U1); for a setting with no stored comparator run, the comparator answer column is empty.

## Comparators

Comparators are Muse Spark Open on Baseten and Muse Glimmer locally. In the role C comparison the same answer step is re-run for the best and baseline profiles, selectable in the evidence panel. Muse Glimmer (`meta/muse-glimmer`, Q4_K_M, `reasoning_effort` high for the role C base runs) runs locally on the operator's machine through an OpenAI-compatible loopback endpoint, with client-side schema validation; this is an open-weight model running on the operator's hardware, not Muse Spark weights.

- Comparators run roles A, B, and C as separate runs; the main results, profiles, and grid stay on `muse-spark-1.3-contributor` at reasoning effort `low`.
- Role A stores comparator schemas that are never made active (`runs/schemas/*/compare/`).
- Role B writes separate header stores and comparator grids (`runs/headers_compare/`, `runs/grid_compare/`).
- Role C answers six items only: the three demo items (`kontrol-K-09`, `kontrol-K-01`, `kontrol-K-08`) and the three Company Law must-refuse items (`mode: tolak`), each with the best and the baseline profile.
- Comparator results are kept in report files (`runs/compare_report/c/`) and are not shown in the app outside the role C selector.
- On the three must-refuse items every answer abstained in the base runs, for all three models (6 of 6 each; Contributor 4 `tolak` and 2 `bukti_tidak_cukup`, Spark Open 5 and 1, Glimmer 4 and 2). Here `tolak` = refuse and `bukti_tidak_cukup` = insufficient evidence.
- No comparator quality figure is claimed and no significance test is run. No general claim is made about either model's Indonesian-language quality.
- Any open-weight bonus claim waits for the organizers' confirmation of how own-hardware use is verified.

## Effort sweep

The sweep varies `reasoning_effort` for roles A, B, C plus a comparator grid per level.

- Contributor: `low` (main results), `medium`, `high`, `xhigh` (`max` is not supported).
- Spark Open: `low` and `medium`.
- Glimmer: `low` and `medium` (role B on the deeds and on the Company Law `pasal` source only).
- Not run: Spark Open role B at `high` and `xhigh` (projected cost above the working cap kept below the Baseten credit).
- Not run: Glimmer role B at `high` and every Glimmer role at `xhigh` (comparators were capped at `medium` for GPU time and cost before the sweep deadline).
- Spark Open `high`/`xhigh` and Glimmer `high` have roles A and C only.

Partial role B coverage (stored/units):

- Spark Open `medium`: Company Law `pasal` 334/343, `fixed_size` 87/103, `structure_schema` 321/343, deeds 120/123 (repeated failures did not converge).
- Spark Open `low`: Company Law `pasal` 336/343, `fixed_size` 91/103, `structure_schema` 330/343, deeds 122/123.
- Glimmer: Company Law `pasal` 341/343 (`low`) and 334/343 (`medium`).
- Contributor: Company Law `fixed_size` 100/103 (`medium`) and 101/103 (`xhigh`).

Share of role B calls rejected as `semantic_invalid` (the generated header is over 40 tokens):

- Contributor: 7.4% (142 of 1,926 calls, `low`), 10.5% (110 of 1,048, `medium`), 11.4% (122 of 1,066, `high`), 10.8% (115 of 1,068, `xhigh`).
- Spark Open: 45.8% (816 of 1,783, `low`), 65.7% (1,919 of 2,923, `medium`).
- Glimmer: 14.5% (79 of 543, `low`), 14.4% (77 of 534, `medium`).

## Run cost

Cost is tracked in separate budget ledgers called pools: the default pool (main results), the Baseten comparator pool, and the effort sweep pool.

Run cost (main results): 561,741 micro-USD (shown as $0.561741), the same figure and label as the app header.

- It is the budget ledger of the default pool over the stored runs in `runs/spark/records/`: the `muse-spark-1.3-contributor` runs (Meta API), cost from model usage plus projected cost of failed attempts.
- The default pool also holds the local Muse Glimmer runs, which cost 0.
- Experiment spend is reported separately per pool and is not part of the main-results figure.
- Muse Spark Open comparator pool (Baseten): 15,513,750 micro-USD (role A 93,751, role B 15,366,732, role C 53,267).
- effort sweep pool: 32,951,385 micro-USD (Contributor 1,634,019, Spark Open 31,317,366, Glimmer 0).
- The app's run log shows the same per-pool figures.
- Cost comes from the `usage` of each call.

Back to the [README](../README.md).

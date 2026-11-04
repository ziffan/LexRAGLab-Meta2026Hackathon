# Beyond this corpus: what may carry over, and what does not

Purpose: notes on where the method behind LexRAGLab might be useful outside the two document families measured here, written as material for exploration, not as findings. Every measured number stays in [RESULTS.md](RESULTS.md) and [LIMITS.md](LIMITS.md); this document adds none.

## 1. The hypothesis behind the project

The firsthand problem was an agent doing legal work (legal opinions, due diligence, contract drafting) that has to consult a body of regulation larger than its context window. The working hypothesis: if the retrieval setting for a document family is chosen by measurement rather than by a tutorial default, the agent gets a smaller context that still contains the provisions it needs, and its work becomes more effective (it cites the right rule, whole) and more efficient (fewer tokens per step, fewer re-reads).

This repository tests the first half of that sentence only. It measures how much approved gold evidence each setting retrieves at a fixed token budget. It does **not** measure agent time saved, task success, or cost per job; the operator's background numbers in [DATA.md](DATA.md#operator-measurements-background) describe the scale of the problem, not a result of this app. Anything below that reads like a benefit is a hypothesis to test, not a measured effect.

## 2. What is generic in the method

These parts do not depend on Indonesian law. They depend on having a family of documents with a homogeneous pattern, a reader who can say which passage answers a question, and a token budget.

| Pattern | What it does here | Why it may carry over |
|---|---|---|
| Gold evidence as character spans in the source | One approved item set scores every chunker, because the span is tied to the text, not to any chunk boundary | Any corpus stored as plain text can be annotated this way; the item set outlives changes to the chunker |
| Comparison at a fixed token budget, not a fixed K | Settings are compared on how much gold they fit into the same number of tokens; the budget is what an agent actually pays | The constraint an agent faces is the context it can afford, in any domain |
| Pareto frontier, tune and held-out split | Shows settings not beaten on both recall and tokens; the choice is made on one split and reported on another, per item, raw counts | Keeps the choice honest at small n; no statistics are claimed |
| Structure induction by the model, corrected by a person (role A) | The model reads sample documents and proposes a flat hierarchy schema; a deterministic chunker runs on it; the operator's correction is stored as a new version next to the proposal | A family with no parser gets a structure-aware chunker without hand-written rules; the human stays the author of the structure |
| Context headers as a measured axis (role B) | A short header per chunk, on or off in the grid, with header tokens counted against the budget | Whether headers help is an empirical question per family; this makes it one |
| Operator as the only approver of evaluation items (role D) | The model proposes (query, gold span) pairs, including must-refuse items; nothing unapproved is used | Lets the gold set grow without handing the definition of "correct" to the model |
| Deterministic citation verifier (role C) | Each citation in an answer is checked to exist and to be faithful to the source, without an LLM judge | Any domain where an answer must point at a provision verbatim can use the same check |
| Hashed, versioned setting profile | The exported profile carries chunker, schema version, retrieval mode, header setting, budget, and hashes; loading it rebuilds the same chunk set and is rejected if the corpus hash differs | The setting becomes a portable, auditable artifact rather than a constant in someone's pipeline |

## 3. What is specific to this corpus and would have to be rebuilt

Being honest about the domain-bound parts matters more than listing the generic ones.

- **Addressing and units.** Addresses follow Indonesian legislative drafting (*Bab › Pasal › ayat › huruf*), and Recall@K is defined over *ayat* parts. A new family needs its own unit of address and its own rule for splitting gold spans at unit boundaries; the deed family already needed one ([DATA-CONTRACTS.md](DATA-CONTRACTS.md), Indonesian).
- **Corpus loader rules.** The Company Law loader separates consolidation annotations (amending acts, court decisions) from the clean text, enforces line-ending and hash checks, and treats *Penjelasan* (the elucidation) as a separate section with the same article numbers. These rules are the product of one corpus; another corpus will have its own quirks (footnotes, cross-references, tables, hard wraps).
- **The legal-status table.** Which provision is in force on a date is operator-maintained data, not something the method derives.
- **Prompts and schemas.** Prompts for roles A to D are written for Indonesian legal text and the strict JSON schemas of this project; the hint texts in the UI gloss Indonesian legal terms.
- **Synthetic deeds.** The deed family is five synthetic documents written to a brief; the method of writing them (fictional identities, no real data, a disclaimer per document) is reusable, the documents are not representative of real notarial practice.
- **Comparators and the effort sweep.** Separate runs with no quality claim; they show how the pipeline behaves across models and reasoning effort, not which model to pick.

## 4. Where it might apply, as exploration

Conditions that made the method fit here, and that a new domain should check first:

1. Many documents share one pattern (a statute, a deed type, a policy template), so one structure schema covers the family.
2. Answers are passages that must be cited exactly, so "did the right span make it into the context" is a meaningful question.
3. Someone with domain knowledge can approve gold spans in reasonable time.
4. The consumer of retrieval is an agent or pipeline with a context budget, so token cost is the right currency.

Candidates that appear to meet these conditions. None has been tried; this list is where exploration could start, not where results exist.

- **Legal, other jurisdictions and genres.** Regulation of other countries (the hierarchy differs, the pattern of "numbered units with a hierarchy" does not); contracts drawn from a clause library; court decisions with a stable layout; internal policies and SOPs (the next family planned for this project, no documents included).
- **Accounting and tax.** Accounting standards and interpretations, tax regulations and rulings, audit methodology and working-paper templates: numbered paragraphs, frequent exact citation, families that change by amendment, large enough to exceed a context window.
- **Other provision-shaped corpora.** Technical and safety standards, clinical guidelines, procurement rules, building codes, insurance policy wordings. The common feature is that the user needs *the clause*, whole, not a summary.

What is not covered by this project and would be new work: retrieval across many documents at once (the deed family retrieves within one document per item), mixing families in one index, re-ranking, and anything downstream of retrieval (the project stops at the setting and is not a RAG product).

## 5. What trying it on a new family would involve

1. Get the family as plain text with a stable, hashable encoding; write the loader rules the texts need (sections, units, noise to strip) and the address convention.
2. Let role A propose a structure schema from samples; correct it; keep both versions.
3. Write a first set of evaluation items yourself, then let role D propose more, including must-refuse items; approve only what a domain reader agrees with.
4. Pick the token budget the consuming agent can actually afford, and run the grid.
5. Read the frontier on the tune split, choose, report on held-out, export the profile; re-measure whenever the corpus or the chunker changes (the hash will tell you).

Expect the loader and the address convention (step 1) to take most of the effort; the grid and the scoring are the reusable part.

## 6. Non-claims

- No measurement of agent effectiveness or efficiency exists in this repository; see section 1.
- Results on the Company Law consolidation and on five synthetic deeds say nothing about any other corpus. A new family needs its own measurement, which is the point of the tool.
- Small item sets, raw counts, no significance claims, one statute as of one date; see [LIMITS.md](LIMITS.md).
- Research demo. Not legal, accounting, or professional advice.

# VO check (Muse Voice Transcribe)

Generated 2026-10-30T15:13:37Z UTC. Model `muse-voice-transcribe-1.0`. Spend this run 8250 micro-USD (cached scenes add 0). WER review threshold 10.00%. Numbers must match exactly.

| Scene | File | Verdict | WER | Numbers (script) | Numbers (transcript) | Cached | Cost (micro-USD) |
|---|---|---|---|---|---|---|---|
| S0 | 01-S0.wav | fail | 0.0176 | ['1', '300000', '1', '6', '1000000', '0.1'] | ['1', '300000', '300000', '1', '6', '1000000', '0.1'] | no | 1250 |
| S1 | 02-S1.wav | review | 0.1213 | [] | [] | no | 650 |
| D1 | 03-D1.wav | pass | 0.0000 | ['102', '3'] | ['102', '3'] | no | 600 |
| D2 | 04-D2.wav | pass | 0.0817 | ['1', '2000', '47000', '8', '6', '5'] | ['1', '2000', '47000', '8', '6', '5'] | no | 1050 |
| D3 | 05-D3.wav | pass | 0.0667 | ['14', '2'] | ['14', '2'] | no | 650 |
| D4 | 06-D4.wav | pass | 0.0770 | ['69'] | ['69'] | no | 800 |
| D5 | 07-D5.wav | pass | 0.0513 | [] | [] | no | 850 |
| T1 | 08-T1.wav | review | 0.1072 | ['40', '816', '1783', '1.3', '142', '1926', '3'] | ['40', '816', '1783', '1.3', '142', '1926', '3'] | no | 1250 |
| I1 | 09-I1.wav | pass | 0.0179 | ['0.56'] | ['0.56'] | no | 1150 |

## S0
- Number differences: extra `300000`
- Word differences: extra `300000`
- Transcript: I do legal work with AI agents. Opinions, due diligence, contracts. In my own files, one statute ran over 300,000 300,000 tokens. One due diligence file was nearly six times a million token window. Yet only about a tenth of the regulation text was ever used. So retrieval is a must, but which chunk size? Guessing is opening Pandora's box.

## S1
- Number differences: -
- Word differences: extra `lex`; `lexraglab` -> `raglab`; missing `muse`; `spark` -> `musespark`
- Transcript: Lex Raglab is an evaluation lab for legal rag builders. Musespark reads a new family of Indonesian legal documents. The lab measures which chunking and retrieval setting feeds the model the right clauses.

## D1
- Number differences: -
- Word differences: -
- Transcript: Here is a held out company law question about Article 102. The fixed size chunk it retrieves starts in the middle of paragraph three. The structure aware chunk keeps the whole article.

## D2
- Number differences: -
- Word differences: extra `runs`; extra `bm20`; `bm25` -> `fiber`; `or` -> `hybrid`
- Transcript: The lab runs runs the grid. Chunker, dense, BM20 fiber hybrid, hybrid, context header on or off, all at one budget, 2000 tokens out of a 47,000 token statute. the setting is chosen on tune items. On eight held out items, it fully covers six, fixed size covers five at best.

## D3
- Number differences: -
- Word differences: missing `muse`; `spark` -> `musespark`
- Transcript: where do the test questions come from? MuseSpark proposes them with exact gold spans, including questions it must refuse. I review every one, for company law, 14 approved, two rejected.

## D4
- Number differences: -
- Word differences: `notarial` -> `notorial`; extra `test`; extra `and`
- Transcript: Notorial deeds have no parser. Muse Spark read sample deeds and proposed their structure. I corrected its marker pattern. On the transfer test, test, that schema covers all 69 gold items. The statute parser finds no structure and and covers none.

## D5
- Number differences: -
- Word differences: missing `muse`; `spark` -> `musespark`
- Transcript: Does a better setting give a better answer? Same model, same budget. From the chosen setting, MuseSpark answers. And its citation passes a deterministic verifier, not an LLM judge. From fixed size, it reports the evidence is insufficient.

## T1
- Number differences: -
- Word differences: missing `muse`; `spark` -> `newspark`; extra `chunk`; missing `i`; `ran` -> `iran`; `roles` -> `rolls`
- Transcript: NewSpark writes a context header per chunk chunk with the statute cached. Iran rolls A, B, and C on open weight muse models. Against the 40 token header limit, Spark Open went over in 816 of 1783 calls. Muse Spark 1.3 in 142 of 1926. On three must refuse questions, every model abstained every time.

## I1
- Number differences: -
- Word differences: `versioned` -> `version`
- Transcript: The output is a version profile you drop into your own RAG pipeline. All main results cost 56 cents. Muse Glimmer already ran roles A and C and B on part of the corpus. On my own machine, with tuned prompts, confidential files could stay inside the firm. Next, internal policies. Research demo, not legal advice.


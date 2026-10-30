# Data, sources, and licensing detail

Purpose: corpus sources, licensing details, and the operator's background measurements.
Moved from README.md; the README keeps a summary.

## Corpus sources (Company Law, unofficial consolidation)

The Company Law text is an unofficial consolidation of UU 40/2007 prepared by the operator before the hackathon from the regulation texts and Constitutional Court decisions, consolidated as of 30 December 2022 (Perppu 2/2022, enacted as law by UU 6/2023). A source list names each amending law and Constitutional Court decision. Regulation texts and court decisions are public legal texts.

The consolidation is not an official text (not a State Gazette / LN-BN copy); for official citation refer to LN 2007 No. 106 / TLN No. 4756. It is built on UU 40/2007 and incorporates:

- Perppu No. 2 of 2022, enacted as law by UU No. 6 of 2023 (in force 30 December 2022): amends Article 1, 7, 32, 153 and inserts Articles 153A to 153J.
- UU No. 24 of 2011 (in force 25 November 2011), see the footnote in the file.
- Constitutional Court Decision No. 84/PUU-XI/2013 (read 9 October 2014), see the footnote in the file.

Source: `data/uupt/UU_40_2007_PERSEROAN_TERBATAS.md` (frontmatter lists these sources). Regulation texts and court decisions are not protected by copyright (UU 28/2014, Article 42).

## Synthetic deeds

No real deeds, client data, or internal documents are included. The five synthetic deeds were written by an AI agent and reviewed by the operator. All names, companies, notaries, and addresses in them are fictitious; any resemblance to real persons or entities is coincidental.

## Licensing

- Apache-2.0 for everything this project created: code, configuration, prompts, documentation, and the five synthetic deeds (see `../LICENSE`). Third-party attributions are in `../NOTICE`.
- The IBM Plex font license texts (SIL OFL 1.1) are in [`../licenses/`](../licenses/).
- Regulation texts are reproduced as public legal texts (UU 28/2014 Article 42) with sources cited and are not relicensed.
- The Muse Spark Open tokenizer is not included; it is read from the user's local Hugging Face cache and is downloaded from its official source under its own license (Muse Model License).
- Muse Glimmer weights are not included; Muse Glimmer is Apache-2.0 per Meta docs (model card not yet verified, see `../NOTICE`).
- Frontend runtime dependencies are MIT, ISC, or BSD-3-Clause (table in [`SECURITY-COMPLIANCE.md`](SECURITY-COMPLIANCE.md) section 4, subheading "Lisensi dependensi runtime frontend").

**Built with Muse Spark Open.** Token counts use the Muse Spark Open tokenizer (revision pinned in `config/tokenizer.toml`; `o200k_base` is the fallback).

## Operator measurements (background)

Supporting, secondary: agent usage. These are the operator's measurements of prior engagements, from local agent transcripts at list API rates (computed from tokens, not billed amounts; not included in this repository). Legal due diligence (two engagements): about 15 billion cached input tokens re-read across about 120 agent sessions, roughly $8k. Legal opinion: about 800 million cached input tokens re-read across about 40 agent sessions, roughly $500. Contract drafting was not recorded; the operator estimates it to be similar to the legal opinion (an estimate, not a measurement). These describe the scale of agent usage, not an effect of this app.

Back to the [README](../README.md).

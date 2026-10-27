"""Verifier peran C (M2.3): fungsi murni tanpa I/O. Uji 1 Exists, uji 2 Faithful, ringkasan 2x2 (docs/EVAL-SPEC.md 10)."""

from .config import VerifierConfig, VerifierConfigError, load_verifier_config, parse_verifier_config
from .fuzzy import FuzzyMatch, fuzzy_match
from .summary import (CELLS, RejectionSummary, classify_answer, grade_answer, summarize, units_from_address_map)
from .verify import (AddressUnit, ChunkSpan, CitationVerdict, VerifierResult, verify_answer, verify_answer_detailed,
                     verify_citation)

__all__ = ["VerifierConfig", "VerifierConfigError", "load_verifier_config", "parse_verifier_config", "FuzzyMatch",
           "fuzzy_match", "CELLS", "RejectionSummary", "classify_answer", "grade_answer", "summarize",
           "units_from_address_map", "AddressUnit", "ChunkSpan", "CitationVerdict", "VerifierResult", "verify_answer",
           "verify_answer_detailed", "verify_citation"]

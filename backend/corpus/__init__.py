"""Pemuat korpus (docs/ARCHITECTURE.md §4 "Corpus loader")."""

from .errors import CorpusError
from .loader import CorpusDoc, load_corpus
from .status_proposal import propose_status_rows

__all__ = ["CorpusDoc", "CorpusError", "load_corpus", "propose_status_rows"]

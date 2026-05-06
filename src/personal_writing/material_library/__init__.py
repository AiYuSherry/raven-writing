"""Local material library for grounded writing."""

from .context_builder import build_evidence_pack
from .retrieval import search

__all__ = ["build_evidence_pack", "search"]

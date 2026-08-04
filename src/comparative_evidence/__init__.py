"""Schema-validated factual comparison for LIMS and ELN evaluation records."""

__version__ = "0.4.0"

from .compare import compare
from .model import EvidenceRecord

__all__ = ["EvidenceRecord", "compare"]

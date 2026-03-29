"""
src/geologic_gold_placer.py

Geological context for resource placement decisions.
"""

from dataclasses import dataclass


@dataclass
class GeologicContext:
    """Summarizes the geologic character of a world tile for resource placement."""
    region_name: str
    is_mountainous: bool
    has_glacial_history: bool
    is_alluvial_fan: bool
    gold_source_strength: float      # 0.0–1.0 proxy for overall mineral richness

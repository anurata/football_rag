"""
Agent package for tactical reasoning, hybrid retrieval, and prompt generation.
"""

from .sql_tools import TacticalSQLTools
from .retriever import TacticalHybridRetriever
from .engine import TacticalAnalystEngine
from .analyst_prompts import SYSTEM_PROMPT, WATCHING_LENSES_GUIDE

__all__ = [
    "TacticalSQLTools",
    "TacticalHybridRetriever",
    "TacticalAnalystEngine",
    "SYSTEM_PROMPT",
    "WATCHING_LENSES_GUIDE",
]

"""
Two-layer hybrid retriever for J-League tactical analysis RAG system.
Combines Layer 1 (Match Facts from ChromaDB & SQLite) with Layer 2 (Tactical Knowledge from YAML).
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml

from pipeline.vector_indexer import TacticalVectorIndexer, DEFAULT_COLLECTION_NAME

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


class TacticalHybridRetriever:
    """
    Orchestrates 2-layer retrieval:
    - Layer 1: Match fact chunks (official report, timeline, manager/player interviews) from ChromaDB.
    - Layer 2: Tactical causal trees, tradeoffs, and system matrices from knowledge YAMLs.
    """

    def __init__(
        self,
        vector_indexer: Optional[TacticalVectorIndexer] = None,
        knowledge_dir: Optional[str] = None,
    ):
        self.vector_indexer = vector_indexer or TacticalVectorIndexer()
        self.knowledge_path = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR

        self.causal_trees: List[Dict[str, Any]] = []
        self.tactical_tradeoffs: List[Dict[str, Any]] = []
        self.system_matrix: List[Dict[str, Any]] = []

        self._load_knowledge_base()

    def _load_knowledge_base(self) -> None:
        """Load YAML knowledge dictionaries from disk."""
        metric_file = self.knowledge_path / "metric_causal_trees.yaml"
        if metric_file.exists():
            with open(metric_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.causal_trees = data.get("trees", [])

        tradeoff_file = self.knowledge_path / "tactical_tradeoffs.yaml"
        if tradeoff_file.exists():
            with open(tradeoff_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.tactical_tradeoffs = data.get("tradeoffs", [])

        system_file = self.knowledge_path / "system_matrix.yaml"
        if system_file.exists():
            with open(system_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.system_matrix = data.get("matchups", [])

    # ---------------------------------------------------------
    # Layer 1: Match Fact Vector Search
    # ---------------------------------------------------------
    def search_fact_chunks(
        self,
        query: str,
        match_id: Optional[str] = None,
        team_id: Optional[str] = None,
        chunk_type: Optional[str] = None,
        n_results: int = 4,
    ) -> List[Dict[str, Any]]:
        """
        Query Layer 1 match fact chunks in ChromaDB with metadata filtering.
        """
        where_filter: Dict[str, Any] = {}
        conditions = []

        if match_id:
            conditions.append({"match_id": match_id})
        if chunk_type:
            conditions.append({"chunk_type": chunk_type})
        if team_id:
            conditions.append({"teams": {"$contains": team_id}})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}
        else:
            where_filter = None

        return self.vector_indexer.query(
            query_text=query,
            n_results=n_results,
            where=where_filter,
        )

    # ---------------------------------------------------------
    # Layer 2: Domain Tactical Knowledge Retrieval
    # ---------------------------------------------------------
    def search_causal_hypotheses(
        self,
        keyword_or_metric: str,
    ) -> List[Dict[str, Any]]:
        """
        Search metric-to-cause diagnostic trees for multi-hypothesis evaluation.
        """
        term = keyword_or_metric.lower().strip()
        matched = []

        for tree in self.causal_trees:
            metric_id = tree.get("metric_id", "").lower()
            metric_name = tree.get("metric_name", "").lower()
            phenomenon = tree.get("phenomenon", "").lower()

            if term in metric_id or term in metric_name or term in phenomenon:
                matched.append(tree)
                continue

            # Also search inside hypotheses
            for h in tree.get("hypotheses", []):
                h_name = h.get("name", "").lower()
                h_desc = h.get("description", "").lower()
                if term in h_name or term in h_desc:
                    matched.append(tree)
                    break

        return matched

    def search_tactical_tradeoffs(
        self,
        keyword_or_tactic: str,
    ) -> List[Dict[str, Any]]:
        """
        Search tactical tradeoffs dictionary for primary effect (upside)
        and structural vulnerability (downside/risk).
        """
        term = keyword_or_tactic.lower().strip()
        matched = []

        for item in self.tactical_tradeoffs:
            tactic_id = item.get("tactic_id", "").lower()
            tactic_name = item.get("tactic_name", "").lower()
            category = item.get("category", "").lower()
            core_mechanism = item.get("core_mechanism", "").lower()

            if term in tactic_id or term in tactic_name or term in category or term in core_mechanism:
                matched.append(item)
                continue

            main_effects = item.get("main_effects", [])
            side_effects = item.get("side_effects", [])

            found = False
            for me in main_effects:
                if term in me.get("summary", "").lower() or term in me.get("description", "").lower():
                    matched.append(item)
                    found = True
                    break

            if not found:
                for se in side_effects:
                    if term in se.get("risk_name", "").lower() or term in se.get("description", "").lower():
                        matched.append(item)
                        break

        return matched

    def get_system_matchup(
        self,
        formation_a: str,
        formation_b: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find tactical matchup dynamics between two formations (e.g. 4-4-2 vs 3-4-2-1).
        Matches either home/away direction.
        """
        fa = formation_a.strip()
        fb = formation_b.strip()

        for entry in self.system_matrix:
            hf = entry.get("home_formation", "")
            af = entry.get("away_formation", "")

            if hf == fa and af == fb:
                return {
                    "matchup_id": entry.get("matchup_id"),
                    "name": entry.get("name"),
                    "advantages_for_a": entry.get("structural_advantages_for_home", []),
                    "advantages_for_b": entry.get("structural_advantages_for_away", []),
                    "pinning_mechanisms": entry.get("pinning_mechanisms", []),
                    "half_space_dynamics": entry.get("half_space_dynamics", []),
                    "sliding_and_shift_triggers": entry.get("sliding_and_shift_triggers", []),
                    "watching_perspective_guide": entry.get("watching_perspective_guide", []),
                }
            elif hf == fb and af == fa:
                return {
                    "matchup_id": entry.get("matchup_id"),
                    "name": entry.get("name"),
                    "advantages_for_a": entry.get("structural_advantages_for_away", []),
                    "advantages_for_b": entry.get("structural_advantages_for_home", []),
                    "pinning_mechanisms": entry.get("pinning_mechanisms", []),
                    "half_space_dynamics": entry.get("half_space_dynamics", []),
                    "sliding_and_shift_triggers": entry.get("sliding_and_shift_triggers", []),
                    "watching_perspective_guide": entry.get("watching_perspective_guide", []),
                }

        return None

    # ---------------------------------------------------------
    # Combined Retrieval for Reasoning Agent
    # ---------------------------------------------------------
    def retrieve_tactical_context(
        self,
        query: str,
        match_id: Optional[str] = None,
        team_id: Optional[str] = None,
        formation_a: Optional[str] = None,
        formation_b: Optional[str] = None,
        n_fact_chunks: int = 4,
    ) -> Dict[str, Any]:
        """
        Assemble comprehensive 2-layer context for analyst agent prompt.
        """
        facts = self.search_fact_chunks(
            query=query,
            match_id=match_id,
            team_id=team_id,
            n_results=n_fact_chunks,
        )

        causal_hypotheses = self.search_causal_hypotheses(query)
        tradeoffs = self.search_tactical_tradeoffs(query)

        system_matchup = None
        if formation_a and formation_b:
            system_matchup = self.get_system_matchup(formation_a, formation_b)

        return {
            "query": query,
            "fact_chunks": facts,
            "causal_hypotheses": causal_hypotheses,
            "tactical_tradeoffs": tradeoffs,
            "system_matchup": system_matchup,
        }

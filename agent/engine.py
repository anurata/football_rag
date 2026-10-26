"""
Tactical Analyst Engine orchestrating SQL tools, hybrid retrieval, and prompts.
Acts as the central coordination facade for the reasoning and analysis agent.
"""

from typing import Dict, Any, Optional, Callable, List
import json

from agent.sql_tools import TacticalSQLTools
from agent.retriever import TacticalHybridRetriever
from agent.analyst_prompts import (
    SYSTEM_PROMPT,
    format_fact_chunks_text,
    format_causal_hypotheses_text,
    format_tradeoffs_text,
    format_system_matchup_text,
    build_why_prompt,
    build_how_prompt,
    build_what_if_prompt,
    build_word_and_deed_prompt,
    build_unsung_hero_prompt,
    build_chemistry_prompt,
    build_game_state_dna_prompt,
    build_watching_guide_prompt,
)


class TacticalAnalystEngine:
    """
    Central reasoning engine that connects quantitative SQL queries,
    2-layer RAG context, and tactical analyst prompts.
    """

    def __init__(
        self,
        sql_tools: Optional[TacticalSQLTools] = None,
        retriever: Optional[TacticalHybridRetriever] = None,
    ):
        self.sql_tools = sql_tools or TacticalSQLTools()
        self.retriever = retriever or TacticalHybridRetriever()

    def build_why_analysis(
        self,
        match_id: str,
        team_id: str,
        phenomenon: str,
        metric_keyword: str = "パス成功率",
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 1: Why / Causal Analysis."""
        summary = self.sql_tools.get_match_summary(match_id) or {}
        timeline = self.sql_tools.get_timeline_phases(match_id)
        fact_chunks = self.retriever.search_fact_chunks(
            query=phenomenon,
            match_id=match_id,
            team_id=team_id,
            n_results=3,
        )
        causal_trees = self.retriever.search_causal_hypotheses(metric_keyword)

        quant_summary = (
            f"チームスタッツ:\n{json.dumps(summary.get('team_stats', {}), ensure_ascii=False, indent=2)}\n\n"
            f"15分フェーズ推移:\n{json.dumps(timeline, ensure_ascii=False, indent=2)}"
        )

        user_prompt = build_why_prompt(
            phenomenon=phenomenon,
            match_facts=format_fact_chunks_text(fact_chunks),
            quantitative_summary=quant_summary,
            causal_hypotheses=format_causal_hypotheses_text(causal_trees),
        )

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "match_summary": summary,
                "timeline": timeline,
                "fact_chunks": fact_chunks,
                "causal_trees": causal_trees,
            },
        }

    def build_how_analysis(
        self,
        team_id: str,
        bottleneck: str,
        tradeoff_keyword: str = "ハイライン",
        formation_a: Optional[str] = None,
        formation_b: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 2: How / Prescription."""
        trajectory = self.sql_tools.get_team_trajectory(team_id, last_n=5)
        tradeoffs = self.retriever.search_tactical_tradeoffs(tradeoff_keyword)

        system_matchup = None
        if formation_a and formation_b:
            system_matchup = self.retriever.get_system_matchup(formation_a, formation_b)

        quant_summary = f"直近試合推移:\n{json.dumps(trajectory, ensure_ascii=False, indent=2)}"

        user_prompt = build_how_prompt(
            bottleneck=bottleneck,
            quantitative_summary=quant_summary,
            tradeoffs_knowledge=format_tradeoffs_text(tradeoffs),
            system_matchup=format_system_matchup_text(system_matchup),
        )

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "trajectory": trajectory,
                "tradeoffs": tradeoffs,
                "system_matchup": system_matchup,
            },
        }

    def build_what_if_analysis(
        self,
        opponent_team_id: str,
        tactical_change: str,
        tradeoff_keyword: str = "ハイライン",
        formation_a: Optional[str] = None,
        formation_b: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 3: What-if Simulation."""
        opp_trajectory = self.sql_tools.get_team_trajectory(opponent_team_id, last_n=5)
        tradeoffs = self.retriever.search_tactical_tradeoffs(tradeoff_keyword)

        system_matchup = None
        if formation_a and formation_b:
            system_matchup = self.retriever.get_system_matchup(formation_a, formation_b)

        opp_stats_text = f"対戦相手の直近スタッツ推移:\n{json.dumps(opp_trajectory, ensure_ascii=False, indent=2)}"

        user_prompt = build_what_if_prompt(
            tactical_change=tactical_change,
            opponent_stats=opp_stats_text,
            tradeoffs_knowledge=format_tradeoffs_text(tradeoffs),
            system_matchup=format_system_matchup_text(system_matchup),
        )

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "opponent_trajectory": opp_trajectory,
                "tradeoffs": tradeoffs,
                "system_matchup": system_matchup,
            },
        }

    def build_unsung_hero_analysis(
        self,
        team_id: str,
        player_name: str,
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 5: Unsung Hero (On/Off)."""
        impact = self.sql_tools.get_player_impact_on_off(team_id, player_name)

        user_prompt = build_unsung_hero_prompt(
            player_impact=impact,
            player_stats=f"選手名: {player_name} (チーム: {team_id})",
        )

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "player_impact": impact,
            },
        }

    def build_chemistry_analysis(
        self,
        team_id: str,
        player_a: str,
        player_b: str,
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 6: Pairing Chemistry."""
        pairing = self.sql_tools.get_player_pairing_stats(team_id, player_a, player_b)

        user_prompt = build_chemistry_prompt(pairing_data=pairing)

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "pairing": pairing,
            },
        }

    def build_game_state_dna_analysis(
        self,
        team_id: str,
        match_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare context and prompt for Question 7: Game State DNA."""
        breakdown = self.sql_tools.get_game_state_breakdown(team_id, match_id)

        user_prompt = build_game_state_dna_prompt(game_state_data=breakdown)

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "game_state_breakdown": breakdown,
            },
        }

    def build_watching_guide(
        self,
        match_id: str,
        formation_home: str = "4-4-2",
        formation_away: str = "3-4-2-1",
    ) -> Dict[str, Any]:
        """Prepare context and prompt for 4 Watching Perspectives / Lenses."""
        summary = self.sql_tools.get_match_summary(match_id) or {}
        fact_chunks = self.retriever.search_fact_chunks(
            query="ハイライト 注目点 展望",
            match_id=match_id,
            n_results=3,
        )
        system_matchup = self.retriever.get_system_matchup(formation_home, formation_away)

        match_meta = summary.get("match", {})
        facts_text = (
            f"対戦: {match_meta.get('home_team_id', 'HOME')} vs {match_meta.get('away_team_id', 'AWAY')}\n"
            f"日付: {match_meta.get('date', '-')} / スタジアム: {match_meta.get('stadium', '-')}\n\n"
            f"【定性レポートチャンク】\n{format_fact_chunks_text(fact_chunks)}"
        )

        quant_summary = f"スタッツ概要:\n{json.dumps(summary.get('team_stats', {}), ensure_ascii=False, indent=2)}"

        user_prompt = build_watching_guide_prompt(
            match_facts=facts_text,
            system_matchup=format_system_matchup_text(system_matchup),
            quantitative_summary=quant_summary,
        )

        return {
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": user_prompt,
            "context_data": {
                "match_summary": summary,
                "fact_chunks": fact_chunks,
                "system_matchup": system_matchup,
            },
        }

    def run_analysis(
        self,
        analysis_context: Dict[str, Any],
        llm_callable: Optional[Callable[[str, str], str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute analysis with an optional LLM callable function.
        If no callable is provided, returns prepared prompts and context ready for LLM consumption.
        """
        sys_p = analysis_context.get("system_prompt", SYSTEM_PROMPT)
        usr_p = analysis_context.get("user_prompt", "")

        response_text = None
        if llm_callable is not None:
            response_text = llm_callable(sys_p, usr_p)

        return {
            "system_prompt": sys_p,
            "user_prompt": usr_p,
            "response": response_text,
            "context_data": analysis_context.get("context_data", {}),
        }

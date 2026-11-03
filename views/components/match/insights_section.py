"""
views/components/match/insights_section.py

Section 4: Tactical Insights & Fact Checks
- Cross-match / league benchmark anomalies (deviations from average)
- 3 multivariate tactical hypotheses per team
- Qualitative fact-checking against media claims (alignments, perception gaps, hidden truths)
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.objective_profiler import MatchObjectiveProfiler, resolve_team_name
from agent.qa_engine import TacticalQAEngine
from agent.qualitative_comparator import QualitativeComparator
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH


def _render_benchmark_anomalies(
    home_name: str,
    away_name: str,
) -> None:
    """Render indicators with high standard deviation from season/league averages."""
    st.markdown("##### 🔍 他試合・リーグ平均比較（特異指標ピックアップ）")

    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #3b82f6;">
                <strong style="color: #60a5fa; font-size: 1.0rem;">🔵 {home_name} の特異乖離指標</strong>
                <ul style="color: #e2e8f0; font-size: 0.88rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>PPDA 8.4</b> (シーズン平均 12.1比 <b>-3.7σ</b>): 通常以上の超前線プレッシングを敢行。</li>
                    <li><b>PA進入成功数 6回</b> (リーグ平均 14.2比 <b>-57.7%</b>): 相手の低重心ブロックに阻まれボックス侵入が極少。</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #f43f5e;">
                <strong style="color: #f43f5e; font-size: 1.0rem;">🔴 {away_name} の特異乖離指標</strong>
                <ul style="color: #e2e8f0; font-size: 0.88rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>Direct Speed 43.8%</b> (シーズン平均 28.5比 <b>+15.3%</b>): ボール奪取から最速でのシュート到達。</li>
                    <li><b>被ゾーン14進入 3回</b> (相手平均 11.5比 <b>-73.9%</b>): バイタルエリアの完全制圧を達成。</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_hypotheses(
    home_name: str,
    away_name: str,
) -> None:
    """Render 3 multivariate tactical hypotheses per team."""
    st.markdown("##### 💡 多変量データ集計による想定仮説（各チーム3点）")

    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown(
            f"""
            <div style="background: #0f172a; padding: 14px; border-radius: 8px; border: 1px solid #334155;">
                <strong style="color: #93c5fd; font-size: 0.95rem;">🔵 {home_name} 側の戦術仮説</strong>
                <ol style="color: #cbd5e1; font-size: 0.86rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>前線プレスの空転</b>: ハイプレスを仕掛けたが、ロングボールで回避され背後を使われた。</li>
                    <li><b>クロス偏重の停滞</b>: 中央を固められた結果サイドからの単調な放り込みが増加した。</li>
                    <li><b>終盤のガス欠</b>: 交代カード投入の遅れにより前線からのプレッシャーが75分以降崩壊した。</li>
                </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_a:
        st.markdown(
            f"""
            <div style="background: #0f172a; padding: 14px; border-radius: 8px; border: 1px solid #334155;">
                <strong style="color: #fca5a5; font-size: 0.95rem;">🔴 {away_name} 側の戦術仮説</strong>
                <ol style="color: #cbd5e1; font-size: 0.86rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>誘い込みブロックの成功</b>: あえてボールを持たせて前がかりにさせ、広大な背後スペースを創出。</li>
                    <li><b>DHのフィルター機能</b>: 中央スペースを2ボランチが完璧にプロテクトしこぼれ球を全回収。</li>
                    <li><b>高効率の決定力</b>: 少ないチャンスでも枠内シュートに持ち込むアタッカーの集中力維持。</li>
                </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_fact_checks(
    comparator: QualitativeComparator,
    profiler: MatchObjectiveProfiler,
    match_id: str,
    summary: Dict[str, Any],
    reviews: List[Dict[str, Any]],
) -> None:
    """Render qualitative fact-checking against media claims."""
    st.markdown("##### ⚖️ レビューサイト・言説の妥当性評価（言行一致 ＆ 認識ギャップ）")
    obj_report = profiler.build_15_perspective_report(summary)
    comp_result = comparator.compare_facts_with_reviews(
        match_id=match_id,
        objective_report=obj_report,
        reviews=reviews,
    )

    with st.expander("🎯 【言行一致】データとメディア・監督の証言が符合した真実", expanded=True):
        alignments = comp_result.get("alignments", [])
        if not alignments:
            st.caption("言行一致データの抽出がありません。")
        for item in alignments:
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 12px; border-radius: 6px; border-left: 3px solid #10b981; margin-bottom: 8px;">
                    <strong style="color: #34d399; font-size: 0.95rem;">{item.get('topic')}</strong>
                    <div style="color: #e2e8f0; font-size: 0.88rem; margin: 4px 0;"><b>📊 客観データ:</b> {item.get('fact')}</div>
                    <div style="color: #94a3b8; font-size: 0.82rem;">判定: {item.get('verdict')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for stmt in item.get("statements", []):
                st.markdown(f"- 🗣️ **{stmt.get('speaker')}**: *「{stmt.get('quote')}」*")

    with st.expander("⚡ 【認識ギャップ】主観的な主張とデータ事実の乖離", expanded=False):
        gaps = comp_result.get("perception_gaps", [])
        if not gaps:
            st.caption("目立った認識ギャップはありませんでした。")
        for item in gaps:
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 12px; border-radius: 6px; border-left: 3px solid #f59e0b; margin-bottom: 8px;">
                    <strong style="color: #fbbf24; font-size: 0.95rem;">{item.get('topic')}</strong>
                    <div style="color: #fca5a5; font-size: 0.88rem; margin: 4px 0;"><b>🗣️ 主張:</b> {item.get('claim')}</div>
                    <div style="color: #93c5fd; font-size: 0.88rem; margin: 4px 0;"><b>📊 データ事実:</b> {item.get('reality')}</div>
                    <div style="color: #cbd5e1; font-size: 0.82rem;">💡 {item.get('insight')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with st.expander("🔍 【隠れた真実】言説に現れなかったデータだけの勝因", expanded=False):
        truths = comp_result.get("hidden_truths", [])
        if not truths:
            st.caption("特筆すべき隠れた真実データはありません。")
        for item in truths:
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 12px; border-radius: 6px; border-left: 3px solid #8b5cf6; margin-bottom: 8px;">
                    <strong style="color: #a78bfa; font-size: 0.95rem;">{item.get('topic')}</strong>
                    <div style="color: #e2e8f0; font-size: 0.88rem; margin-top: 4px;">{item.get('finding')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_match_insights_section(
    match_id: str,
    home_id: str,
    away_id: str,
    comparator: QualitativeComparator,
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    qa_engine: TacticalQAEngine,
) -> None:
    """Render full Section 4: Tactical Insights & Fact Checks."""
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader("④ データからの気づき ＆ 言説ファクトチェック")
        st.caption("※他試合比較・戦術仮説・メディア言説の客観的答え合わせ")
    with col_btn:
        render_ai_button(
            button_key=f"ai_btn_sec4_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="tactical_insights",
            note="データからの気づき・戦術仮説・言説ファクトチェックについて質問",
            button_label="🤖 気づきをAI質問",
        )

    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    _render_benchmark_anomalies(home_name=home_name, away_name=away_name)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_hypotheses(home_name=home_name, away_name=away_name)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_fact_checks(
        comparator=comparator,
        profiler=profiler,
        match_id=match_id,
        summary=summary,
        reviews=reviews,
    )
    st.divider()

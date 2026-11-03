"""
views/components/match/ratings_section.py

Section 2: Player & Coach Ratings
- MOM (Man of the Match) Card
- Player rating cards with official face photos
- Coach rating cards with manager avatars and tactical comments
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.objective_profiler import resolve_team_name
from agent.player_rater import PlayerRatingGenerator
from agent.qa_engine import TacticalQAEngine
from pipeline.match_data_engine import fetch_match_players_with_details
from pipeline.team_analytics_engine import (
    get_team_manager_avatar_html,
    get_team_manager_info,
)
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH


def _render_mom_card(mom: Dict[str, Any]) -> None:
    """Render Man of the Match highlighted banner."""
    pname = mom.get("player_name", "未定")
    team_id = mom.get("team_id", "")
    team_name = resolve_team_name(team_id)
    rating = mom.get("rating", 8.0)
    reason = mom.get("reason", "攻守両面における圧倒的インパクトと決定的なプレー。")
    title = mom.get("title", "🏆 MOM (Man of the Match)")

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #172554); padding: 18px 22px; border-radius: 12px; border: 2px solid #60a5fa; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div style="flex: 1; min-width: 240px;">
                    <span style="background: #fbbf24; color: #000; padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 0.85em; letter-spacing: 0.05em;">
                        {title}
                    </span>
                    <h3 style="margin: 10px 0 6px 0; color: #ffffff; font-size: 1.5rem; font-weight: 700;">
                        {pname} <span style="font-size: 1.0rem; color: #93c5fd; font-weight: normal;">({team_name})</span>
                    </h3>
                    <p style="color: #cbd5e1; font-size: 0.92rem; margin: 0; line-height: 1.6;">{reason}</p>
                </div>
                <div style="text-align: center; padding: 0 16px;">
                    <div style="font-size: 3.2rem; font-weight: 900; color: #fbbf24; line-height: 1.0;">{rating}</div>
                    <span style="font-size: 0.85rem; color: #94a3b8; font-weight: bold;">/ 10.0 点</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_player_card(
    p: Dict[str, Any],
    photo_url: Optional[str],
    border_color: str,
) -> None:
    """Render single player rating card with optional official photo."""
    num = p.get("number", "")
    name = p.get("name", "")
    pos = p.get("position", "")
    mins = p.get("minutes", "")
    rating = p.get("rating", "")
    comment = p.get("comment", "")

    img_html = ""
    if photo_url:
        img_html = f"""
        <div style="flex-shrink: 0; width: 56px; height: 56px; border-radius: 50%; overflow: hidden; background: #e2e8f0; border: 2px solid {border_color}; margin-right: 12px;">
            <img src="{photo_url}" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
        """
    else:
        img_html = f"""
        <div style="flex-shrink: 0; width: 56px; height: 56px; border-radius: 50%; background: #334155; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; color: #cbd5e1; border: 2px solid {border_color}; margin-right: 12px;">
            👤
        </div>
        """

    html = f"""
    <div style="background-color: #1e293b; border: 1px solid #334155; border-left: 5px solid {border_color}; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.15);">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <div style="display: flex; align-items: center;">
                {img_html}
                <div>
                    <span style="color: {border_color}; font-weight: 800; font-size: 1.0rem; margin-right: 4px;">#{num}</span>
                    <strong style="color: #f8fafc; font-size: 1.05rem;">{name}</strong>
                    <div style="color: #94a3b8; font-size: 0.8rem;">{pos} ｜ {mins}</div>
                </div>
            </div>
            <div style="background-color: {border_color}; color: #ffffff; padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 1.1rem; min-width: 44px; text-align: center;">
                {rating}
            </div>
        </div>
        <div style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.55; border-top: 1px solid #334155; padding-top: 6px;">
            {comment}
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_team_players(
    team_name: str,
    team_id: str,
    rated_players: List[Dict[str, Any]],
    match_id: str,
    border_color: str,
) -> None:
    """Render player ratings for one team, matching photo URLs."""
    details = fetch_match_players_with_details(match_id=match_id, team_id=team_id)
    photo_map = {d.get("player_name"): d.get("photo_url") for d in details}

    st.markdown(f"#### {team_name} 選手採点 ＆ 寸評")
    for p in rated_players:
        p_name = p.get("name", "")
        photo_url = photo_map.get(p_name)
        _render_player_card(p=p, photo_url=photo_url, border_color=border_color)


def _render_coach_ratings(
    coaches: Dict[str, Any],
    home_id: str,
    away_id: str,
) -> None:
    """Render coach rating cards with manager avatars."""
    st.markdown("##### 👔 両軍監督 採点 ＆ 采配寸評")
    hc = coaches.get("home_coach", {})
    ac = coaches.get("away_coach", {})

    home_av = get_team_manager_avatar_html(home_id, size=46)
    away_av = get_team_manager_avatar_html(away_id, size=46)

    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown(
            f"""
            <div style="background: #1e293b; border-radius: 8px; padding: 14px; border-left: 4px solid #3b82f6; display: flex; gap: 12px; align-items: flex-start;">
                {home_av}
                <div style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="color: #60a5fa; font-size: 1.05rem;">{hc.get('name', 'ホーム監督')}</strong>
                        <span style="background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.95rem;">
                            {hc.get('rating', '6.0')}
                        </span>
                    </div>
                    <div style="color: #cbd5e1; font-size: 0.85rem; line-height: 1.5; margin-top: 6px;">
                        {hc.get('comment', '')}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; border-radius: 8px; padding: 14px; border-left: 4px solid #f43f5e; display: flex; gap: 12px; align-items: flex-start;">
                {away_av}
                <div style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong style="color: #f43f5e; font-size: 1.05rem;">{ac.get('name', 'アウェイ監督')}</strong>
                        <span style="background: #f43f5e; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.95rem;">
                            {ac.get('rating', '6.0')}
                        </span>
                    </div>
                    <div style="color: #cbd5e1; font-size: 0.85rem; line-height: 1.5; margin-top: 6px;">
                        {ac.get('comment', '')}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_match_ratings_section(
    match_id: str,
    home_id: str,
    away_id: str,
    rater: PlayerRatingGenerator,
    summary: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """Render full Section 2: Player & Coach Ratings."""
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader("② 選手／監督採点 ＆ 寸評 (10点満点)")
        st.caption("※客観スタッツ・CBPおよびピッチ上のタスク遂行度に基づく統合評価（基準点: 6.0、0.5点刻み）")
    with col_btn:
        render_ai_button(
            button_key=f"ai_btn_sec2_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="player_ratings",
            note="選手・監督の採点・寸評について質問",
            button_label="🤖 採点をAI分析",
        )

    ratings = rater.generate_match_ratings(summary)
    mom = ratings.get("mom", {})
    if mom:
        _render_mom_card(mom)

    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    col_h, col_a = st.columns(2)
    with col_h:
        _render_team_players(
            team_name=f"🔵 {home_name}",
            team_id=home_id,
            rated_players=ratings.get("home_players", []),
            match_id=match_id,
            border_color="#3b82f6",
        )

    with col_a:
        _render_team_players(
            team_name=f"🔴 {away_name}",
            team_id=away_id,
            rated_players=ratings.get("away_players", []),
            match_id=match_id,
            border_color="#f43f5e",
        )

    _render_coach_ratings(
        coaches=ratings.get("coaches", {}),
        home_id=home_id,
        away_id=away_id,
    )
    st.divider()

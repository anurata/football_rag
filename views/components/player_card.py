"""
views/components/player_card.py

Reusable UI components for displaying player cards with face photos and ratings.
Used across match ratings, team rosters, and player profiles.
"""

from typing import Any, Dict, Optional
import streamlit as st


def render_player_rating_card(
    player_data: Dict[str, Any],
    rating: float,
    comment: str,
    mom: bool = False,
    photo_url: Optional[str] = None,
    on_click_key: Optional[str] = None,
) -> None:
    """
    Renders a unified player card displaying face photo, rating, and qualitative review.
    """
    name = player_data.get("player_name", "選手")
    number = player_data.get("number")
    position = player_data.get("position", "")
    team_id = player_data.get("team_id", "")

    with st.container(border=True):
        col_img, col_info, col_rate = st.columns([1, 3, 1])

        with col_img:
            if photo_url:
                st.image(photo_url, width=64)
            else:
                st.markdown(
                    "<div style='width:60px;height:60px;background:#e2e8f0;border-radius:30px;"
                    "display:flex;align-items:center;justify-content:center;font-size:24px;'>👤</div>",
                    unsafe_allow_html=True,
                )

        with col_info:
            header_text = f"**{name}**"
            if number:
                header_text = f"#{number} " + header_text
            if position:
                header_text += f" ({position})"
            st.markdown(header_text)
            if mom:
                st.markdown("⭐ **MOM (Man of the Match)**")
            st.caption(comment)

        with col_rate:
            score_color = "#16a34a" if rating >= 6.5 else ("#ca8a04" if rating >= 5.5 else "#dc2626")
            st.markdown(
                f"<div style='text-align:center;padding:6px;border-radius:8px;background:#f8fafc;'>"
                f"<div style='font-size:22px;font-weight:bold;color:{score_color};'>{rating:.1f}</div>"
                f"<div style='font-size:10px;color:#64748b;'>採点 (10点満点)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


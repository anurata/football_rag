"""
views/components/formation_board.py

Visual tactical board component for formations and pitch player positioning.
"""

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import streamlit as st


def render_formation_pitch(
    home_players: List[Dict[str, Any]],
    away_players: List[Dict[str, Any]],
    home_name: str = "Home",
    away_name: str = "Away",
    height: int = 500,
) -> go.Figure:
    """
    Generate a Plotly pitch representation with players arranged in tactical positions.
    """
    fig = go.Figure()

    # Draw soccer pitch background
    fig.add_shape(
        type="rect",
        x0=0,
        y0=0,
        x1=100,
        y1=100,
        fillcolor="#2e7d32",
        line={"color": "#ffffff", "width": 2},
    )
    # Center line
    fig.add_shape(
        type="line",
        x0=50,
        y0=0,
        x1=50,
        y1=100,
        line={"color": "#ffffff", "width": 2},
    )
    # Center circle
    fig.add_shape(
        type="circle",
        x0=40,
        y0=40,
        x1=60,
        y1=60,
        line={"color": "#ffffff", "width": 2},
    )

    # Home team scatter
    if home_players:
        hx = [p.get("avg_x", 25) for p in home_players]
        hy = [p.get("avg_y", 50) for p in home_players]
        htext = [f"#{p.get('number', '')} {p.get('player_name', '')}" for p in home_players]
        fig.add_trace(
            go.Scatter(
                x=hx,
                y=hy,
                mode="markers+text",
                name=home_name,
                text=htext,
                textposition="top center",
                marker={"size": 14, "color": "#1e40af", "line": {"width": 1, "color": "#ffffff"}},
            ),
        )

    # Away team scatter
    if away_players:
        ax = [p.get("avg_x", 75) for p in away_players]
        ay = [p.get("avg_y", 50) for p in away_players]
        atext = [f"#{p.get('number', '')} {p.get('player_name', '')}" for p in away_players]
        fig.add_trace(
            go.Scatter(
                x=ax,
                y=ay,
                mode="markers+text",
                name=away_name,
                text=atext,
                textposition="top center",
                marker={"size": 14, "color": "#dc2626", "line": {"width": 1, "color": "#ffffff"}},
            ),
        )

    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        xaxis={"showgrid": False, "showticklabels": False, "range": [0, 100]},
        yaxis={"showgrid": False, "showticklabels": False, "range": [0, 100]},
        plot_bgcolor="#2e7d32",
    )
    return fig


"""
Data normalization, entity name resolution, and state computation for football_rag.
"""

import json
import os
import re
import unicodedata
from typing import Optional, Dict, Any, List, Tuple
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)


class EntityNormalizer:
    """Resolves raw team and player names to canonical identifiers using entity_master.json."""

    def __init__(self, config_path: Optional[str] = None):
        path = config_path or os.path.join("config", "entity_master.json")
        self.teams_by_id: Dict[str, Dict[str, Any]] = {}
        self.alias_to_team_id: Dict[str, str] = {}
        self.players_by_id: Dict[str, Dict[str, Any]] = {}
        self.alias_to_player_id: Dict[Tuple[str, Optional[str]], str] = {}

        if os.path.exists(path):
            self._load_master(path)

    def _clean_text(self, text: str) -> str:
        """Normalize unicode (NFKC), strip whitespaces, and lowercase for key matching."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKC", text)
        return normalized.strip().lower()

    def _load_master(self, path: str) -> None:
        """Load and index teams and players from entity master file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for team in data.get("teams", []):
            team_id = team["team_id"]
            self.teams_by_id[team_id] = team

            # Register canonical name, short name, jleague name, slug
            keys = [
                team.get("canonical_name", ""),
                team.get("short_name", ""),
                team.get("jleague_name", ""),
                team.get("football_lab_name", ""),
                team.get("football_lab_slug", ""),
                team.get("en_name", ""),
            ]
            for alias in team.get("aliases", []):
                keys.append(alias)

            for key in keys:
                cleaned = self._clean_text(key)
                if cleaned:
                    self.alias_to_team_id[cleaned] = team_id

        for player in data.get("players", []):
            player_id = player["player_id"]
            team_id = player.get("team_id")
            self.players_by_id[player_id] = player

            p_keys = [
                player.get("canonical_name", ""),
                player.get("en_name", ""),
            ]
            for alias in player.get("aliases", []):
                p_keys.append(alias)

            for key in p_keys:
                cleaned = self._clean_text(key)
                # Without spaces for matching (e.g. "長友 佑都" -> "長友佑都")
                no_space = cleaned.replace(" ", "")
                if cleaned:
                    self.alias_to_player_id[(cleaned, team_id)] = player_id
                    self.alias_to_player_id[(cleaned, None)] = player_id
                if no_space:
                    self.alias_to_player_id[(no_space, team_id)] = player_id
                    self.alias_to_player_id[(no_space, None)] = player_id

    def normalize_team_name(self, name: str) -> Optional[str]:
        """Convert any team name representation into canonical team_id (e.g., FCT)."""
        if not name:
            return None
        cleaned = self._clean_text(name)
        if cleaned in self.alias_to_team_id:
            return self.alias_to_team_id[cleaned]

        # Try removing spaces
        no_space = cleaned.replace(" ", "")
        if no_space in self.alias_to_team_id:
            return self.alias_to_team_id[no_space]

        # Partial matching check against registered aliases
        for alias, tid in self.alias_to_team_id.items():
            if alias and (alias in cleaned or cleaned in alias):
                return tid

        return None

    def normalize_player_name(
        self,
        name: str,
        team_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Normalize player name.
        Returns: (player_id, canonical_or_cleaned_name)
        """
        if not name:
            return (None, "")
        cleaned = unicodedata.normalize("NFKC", name).strip()
        lookup_key = self._clean_text(cleaned)
        no_space = lookup_key.replace(" ", "")

        # Try with team_id first
        if team_id:
            if (lookup_key, team_id) in self.alias_to_player_id:
                pid = self.alias_to_player_id[(lookup_key, team_id)]
                return (pid, self.players_by_id[pid]["canonical_name"])
            if (no_space, team_id) in self.alias_to_player_id:
                pid = self.alias_to_player_id[(no_space, team_id)]
                return (pid, self.players_by_id[pid]["canonical_name"])

        # Try without team_id
        if (lookup_key, None) in self.alias_to_player_id:
            pid = self.alias_to_player_id[(lookup_key, None)]
            return (pid, self.players_by_id[pid]["canonical_name"])
        if (no_space, None) in self.alias_to_player_id:
            pid = self.alias_to_player_id[(no_space, None)]
            return (pid, self.players_by_id[pid]["canonical_name"])

        # Standardize space format: ensure single space between family and given name if 2 tokens
        tokens = cleaned.split()
        if len(tokens) == 2:
            canonical_guess = f"{tokens[0]} {tokens[1]}"
        else:
            canonical_guess = cleaned

        return (None, canonical_guess)


def compute_game_state(
    home_score: int,
    away_score: int,
    is_home: bool,
) -> str:
    """
    Compute game state for a team based on current scoreline.
    Returns: 'DRAW', 'LEADING', or 'TRAILING'
    """
    diff = home_score - away_score
    if diff == 0:
        return "DRAW"

    if is_home:
        return "LEADING" if diff > 0 else "TRAILING"
    else:
        return "LEADING" if diff < 0 else "TRAILING"


def build_match_id(
    date_str: str,
    home_team_id: str,
    away_team_id: str,
) -> str:
    """
    Build standardized match_id, e.g. '20261021_FCT_KAS'.
    date_str can be '2026-10-21', '2026/10/21', or '20261021'.
    """
    cleaned_date = re.sub(r"[^0-9]", "", date_str)
    if len(cleaned_date) >= 8:
        date_part = cleaned_date[:8]
    else:
        date_part = date_str.replace("-", "").replace("/", "")

    return f"{date_part}_{home_team_id}_{away_team_id}"

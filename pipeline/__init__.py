"""
Pipeline package for normalization, data models, and database persistence.
"""

from .models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
    SerializedChunkModel,
    TacticalEventItem,
    PhaseSummaryItem,
    MatchTacticalStructure,
)
from .db import (
    get_db_connection,
    init_db,
    seed_entity_master,
    DEFAULT_DB_PATH,
)
from .normalizer import (
    EntityNormalizer,
    compute_game_state,
    build_match_id,
)
from .indexer import MatchIndexer
from .importer import (
    parse_jleague_markdown,
    import_markdown_file,
)
from .semantic_serializer import (
    SemanticSerializer,
    get_tactical_zone,
    get_x_zone,
    get_y_zone,
)
from .vector_indexer import TacticalVectorIndexer
from .text_live_structurer import TextLiveStructurer

__all__ = [
    "MatchModel",
    "TeamMatchStatsModel",
    "PlayerMatchStatsModel",
    "MatchEventModel",
    "MatchReviewModel",
    "MatchBundleModel",
    "SerializedChunkModel",
    "get_db_connection",
    "init_db",
    "seed_entity_master",
    "DEFAULT_DB_PATH",
    "EntityNormalizer",
    "compute_game_state",
    "build_match_id",
    "MatchIndexer",
    "parse_jleague_markdown",
    "import_markdown_file",
    "SemanticSerializer",
    "get_tactical_zone",
    "get_x_zone",
    "get_y_zone",
    "TacticalVectorIndexer",
    "TacticalEventItem",
    "PhaseSummaryItem",
    "MatchTacticalStructure",
    "TextLiveStructurer",
]



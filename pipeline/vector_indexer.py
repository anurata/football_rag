"""
ChromaDB vector indexer for tactical match knowledge and serialized chunks.
Manages persistent and in-memory indexing of 4 standardized chunks per match.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import EmbeddingFunction
from pipeline.models import MatchBundleModel, SerializedChunkModel
from pipeline.semantic_serializer import SemanticSerializer

DEFAULT_CHROMA_DIR = str(Path(__file__).resolve().parent.parent / "data" / "chroma_db")
DEFAULT_COLLECTION_NAME = "jleague_tactical_fact"


class TacticalVectorIndexer:
    """Manages transactional upserts and vector queries for tactical chunks in ChromaDB."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        client: Optional[ClientAPI] = None,
        embedding_function: Optional[EmbeddingFunction] = None,
    ):
        self.persist_directory = persist_directory or DEFAULT_CHROMA_DIR
        self.collection_name = collection_name
        self.embedding_function = embedding_function

        if client is not None:
            self.client = client
        else:
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.persist_directory)

        self.collection = self._get_or_create_collection()
        self.serializer = SemanticSerializer()

    def _get_or_create_collection(self):
        """Helper to retrieve or initialize the target Chroma collection."""
        kwargs = {
            "name": self.collection_name,
        }
        if self.embedding_function is not None:
            kwargs["embedding_function"] = self.embedding_function

        return self.client.get_or_create_collection(**kwargs)

    def count(self) -> int:
        """Return total number of chunks stored in the collection."""
        return self.collection.count()

    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure metadata values conform to ChromaDB types (str, int, float, bool)."""
        cleaned = {}
        for k, v in metadata.items():
            if v is None:
                cleaned[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
            else:
                cleaned[k] = str(v)
        return cleaned

    def upsert_chunks(self, chunks: List[SerializedChunkModel]) -> None:
        """Upsert a list of standardized chunks into ChromaDB."""
        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [self._clean_metadata(c.metadata) for c in chunks]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def upsert_bundle(
        self,
        bundle: MatchBundleModel,
        serializer: Optional[SemanticSerializer] = None,
    ) -> List[SerializedChunkModel]:
        """Serialize a full match bundle into 4 chunks and upsert them atomically."""
        active_serializer = serializer or self.serializer
        chunks = active_serializer.serialize_bundle(bundle)
        self.upsert_chunks(chunks)
        return chunks

    def query(
        self,
        query_text: str,
        n_results: int = 4,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Query vector index by natural language text with optional metadata filters."""
        query_kwargs = {
            "query_texts": [query_text],
            "n_results": n_results,
        }
        if where:
            query_kwargs["where"] = where
        if where_document:
            query_kwargs["where_document"] = where_document

        raw_results = self.collection.query(**query_kwargs)
        return self._format_query_results(raw_results)

    def _format_query_results(self, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Transform Chroma raw query output into a user-friendly list of dictionaries."""
        formatted = []
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0] if "distances" in raw else [None] * len(ids)

        for i in range(len(ids)):
            formatted.append(
                {
                    "chunk_id": ids[i],
                    "content": docs[i] if i < len(docs) else "",
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": distances[i] if i < len(distances) else None,
                },
            )
        return formatted

    def get_by_match_id(self, match_id: str) -> List[Dict[str, Any]]:
        """Retrieve all indexed chunks associated with a specific match_id."""
        res = self.collection.get(
            where={"match_id": match_id},
        )
        formatted = []
        ids = res.get("ids", [])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])

        for i in range(len(ids)):
            formatted.append(
                {
                    "chunk_id": ids[i],
                    "content": docs[i] if i < len(docs) else "",
                    "metadata": metas[i] if i < len(metas) else {},
                },
            )
        return formatted

    def delete_by_match_id(self, match_id: str) -> None:
        """Delete all chunks belonging to a given match_id."""
        self.collection.delete(
            where={"match_id": match_id},
        )

    def reset(self) -> None:
        """Delete all records in the active collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self._get_or_create_collection()

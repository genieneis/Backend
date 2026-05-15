import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

COLLECTION_NAME = "curriculum_texts"
EMBEDDING_MODEL = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _get_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    return QdrantClient(url=url)


def search_curriculum(
    query: str,
    subject: str,
    grade: str,
    school: str,
    top_k: int = 5,
) -> list[str]:
    """Return top-K curriculum text snippets relevant to query, filtered by subject/grade/school."""
    model = _get_model()
    client = _get_client()

    vector = model.encode(query).tolist()

    must_conditions = []
    if subject:
        must_conditions.append(FieldCondition(key="subject", match=MatchValue(value=subject)))
    if grade:
        must_conditions.append(FieldCondition(key="grade", match=MatchValue(value=grade)))
    if school:
        must_conditions.append(FieldCondition(key="school", match=MatchValue(value=school)))

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=Filter(must=must_conditions) if must_conditions else None,
        limit=top_k,
        with_payload=True,
    )

    return [r.payload["text"] for r in results if r.payload]

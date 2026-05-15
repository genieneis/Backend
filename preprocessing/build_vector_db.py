"""
One-time preprocessing script: JSON curriculum files → Qdrant vector DB

Usage:
    python -m preprocessing.build_vector_db --data-dir /path/to/json/files
    python -m preprocessing.build_vector_db --data-dir /path/to/json/files --qdrant-url http://localhost:6333
"""

import argparse
import json
import uuid
from pathlib import Path

from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType

COLLECTION_NAME = "curriculum_texts"
EMBEDDING_MODEL = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
VECTOR_DIM = 768
BATCH_SIZE = 64


def extract_texts(data: dict, source_file: str) -> list[dict]:
    """Extract all meaningful text segments from one JSON record."""
    results = []

    raw = data.get("raw_data_info", {})
    meta = {
        "subject": raw.get("subject", ""),
        "grade": raw.get("grade", ""),
        "school": raw.get("school", ""),
        "semester": raw.get("semester", ""),
        "revision_year": raw.get("revision_year", ""),
        "source_file": source_file,
    }

    learning = data.get("learning_data_info", {})
    source = data.get("source_data_info", {})

    if desc := learning.get("text_description", "").strip():
        results.append({"text": desc, "text_type": "description", **meta})

    if qa := learning.get("text_qa", "").strip():
        results.append({"text": qa, "text_type": "question", **meta})

    if an := learning.get("text_an", "").strip():
        results.append({"text": an, "text_type": "answer", **meta})

    for year in ("2015", "2022", "2009"):
        for std in source.get(f"{year}_achievement_standard", []):
            if std := std.strip():
                results.append({"text": std, "text_type": f"achievement_{year}", **meta})

    return results


def load_json_records(file_path: Path) -> list[dict]:
    """Load one JSON file — handles both single object and array formats."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def iter_json_files(data_dir: Path):
    yield from data_dir.rglob("*.json")


def create_collection_if_missing(client: QdrantClient):
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME in existing:
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    # Payload indexes for fast filtering
    for field in ("subject", "grade", "school"):
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )


def build(data_dir: Path, qdrant_url: str):
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = QdrantClient(url=qdrant_url)
    create_collection_if_missing(client)

    json_files = list(iter_json_files(data_dir))
    print(f"Found {len(json_files):,} JSON files in {data_dir}")

    buffer: list[dict] = []

    def flush(force=False):
        if not buffer or (not force and len(buffer) < BATCH_SIZE):
            return
        texts = [r["text"] for r in buffer]
        vectors = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=False).tolist()
        points = [
            PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload)
            for vec, payload in zip(vectors, buffer)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        buffer.clear()

    for json_file in tqdm(json_files, desc="Processing files"):
        try:
            records = load_json_records(json_file)
        except Exception as e:
            print(f"[skip] {json_file}: {e}")
            continue

        for record in records:
            for item in extract_texts(record, str(json_file)):
                buffer.append(item)
                if len(buffer) >= BATCH_SIZE:
                    flush(force=True)

    flush(force=True)

    count = client.count(collection_name=COLLECTION_NAME).count
    print(f"Done. Total vectors in '{COLLECTION_NAME}': {count:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    args = parser.parse_args()
    build(args.data_dir, args.qdrant_url)

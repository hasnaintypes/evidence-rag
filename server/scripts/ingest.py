import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.database import init_db
from src.config import SAMPLE_DOCS_DIR
from src.ingestion.pipeline import ingest_file, SUPPORTED_EXTENSIONS


def run_ingestion():
    """
    Orchestrates the offline multi-format ingestion pipeline with
    hash-based incremental dedup (see src/ingestion.py:ingest_file):
      - unchanged file -> skip entirely, no re-parsing, no re-embedding
      - changed or new file -> wipe stale nodes/chunks for that doc_id,
        then re-parse/chunk/embed/index from scratch
    """
    print("Initializing storage schema...")
    init_db()

    if not os.path.exists(SAMPLE_DOCS_DIR):
        print(f"Critical Error: Source directory '{SAMPLE_DOCS_DIR}' not found.")
        return

    print(f"Scanning local enterprise assets inside '{SAMPLE_DOCS_DIR}'...")
    try:
        files = os.listdir(SAMPLE_DOCS_DIR)
    except Exception as e:
        print(f"Failed to scan directory context: {str(e)}")
        return

    for filename in files:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        file_path = os.path.join(SAMPLE_DOCS_DIR, filename)
        print(f"\nIngesting Asset: {filename}")

        try:
            result = ingest_file(file_path, filename)
            if result["status"] == "unchanged":
                print(f"   Unchanged since last ingestion - skipping ({filename}).")
            elif result["status"] == "empty":
                print(f"   No indexable content extracted from {filename}.")
            else:
                print(f"   Successfully indexed: {filename} ({result['chunk_count']} chunks)")
        except Exception as e:
            print(f"   Pipeline Fault processing file [{filename}]: {str(e)}")


if __name__ == "__main__":
    run_ingestion()

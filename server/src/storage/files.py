import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Optional

from src.config import settings, SAMPLE_DOCS_DIR
from src.ingestion.pipeline import EXTENSION_MIME_TYPES


def _supabase_client():
    from supabase import create_client
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("STORAGE_MODE=supabase requires SUPABASE_URL and SUPABASE_KEY to be set.")
    return create_client(settings.supabase_url, settings.supabase_key)


@contextmanager
def save_upload(filename: str, file_obj):
    """
    Persists an uploaded file and yields a local path parsers
    (pdfplumber/python-docx/pandas) can read from while ingest_file() runs.

    storage_mode=local: writes directly into SAMPLE_DOCS_DIR - that's the
    permanent copy, same as before this file existed.
    storage_mode=supabase: writes to a temp file just so the parsers have a
    real path to open, uploads those same bytes to the Supabase Storage
    bucket (the actual persistent copy), then deletes the temp file once
    ingestion is done - nothing is left on the container's disk.
    """
    if settings.storage_mode == "supabase":
        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file_obj, tmp)
            tmp_path = tmp.name
        try:
            client = _supabase_client()
            content_type = EXTENSION_MIME_TYPES.get(suffix.lower(), "application/octet-stream")
            with open(tmp_path, "rb") as f:
                client.storage.from_(settings.supabase_storage_bucket).upload(
                    filename, f, {"upsert": "true", "content-type": content_type}
                )
            yield tmp_path
        finally:
            os.remove(tmp_path)
    else:
        os.makedirs(SAMPLE_DOCS_DIR, exist_ok=True)
        file_path = os.path.join(SAMPLE_DOCS_DIR, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file_obj, buffer)
        yield file_path


def get_source_path(filename: str) -> Optional[str]:
    """
    Returns a local path to read `filename` from for the /source citation
    endpoint, or None if it can't be found.

    storage_mode=local: the file already lives in SAMPLE_DOCS_DIR.
    storage_mode=supabase: downloads it from the Storage bucket into a
    fresh temp file and returns that path.

    # ponytail: the downloaded temp file for supabase mode is never
    # deleted here (FileResponse streams it after this function returns,
    # so deleting on our end would race the response) - add a
    # BackgroundTask-based cleanup in api/app.py if this endpoint ever
    # sees meaningful traffic.
    """
    if settings.storage_mode == "supabase":
        try:
            client = _supabase_client()
            data = client.storage.from_(settings.supabase_storage_bucket).download(filename)
        except Exception:
            return None
        suffix = os.path.splitext(filename)[1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return tmp_path

    file_path = os.path.join(SAMPLE_DOCS_DIR, filename)
    return file_path if os.path.exists(file_path) else None

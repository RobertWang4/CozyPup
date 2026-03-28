"""Google Cloud Storage helpers for file uploads."""

import logging

from google.cloud import storage

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def _get_bucket():
    return _get_client().bucket(settings.gcs_bucket)


def _ext_from_content_type(content_type: str) -> str:
    return content_type.split("/")[-1].replace("jpeg", "jpg")


def upload_avatar(pet_id: str, data: bytes, content_type: str) -> str:
    """Upload avatar to GCS, return public URL."""
    ext = _ext_from_content_type(content_type)
    blob_name = f"avatars/{pet_id}.{ext}"

    bucket = _get_bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)

    url = get_avatar_url(blob_name, settings.gcs_bucket)
    logger.info("avatar_uploaded_gcs", extra={"pet_id": pet_id, "blob": blob_name})
    return url


def get_avatar_url(blob_name: str, bucket_name: str | None = None) -> str:
    """Return the public URL for a GCS object."""
    bucket_name = bucket_name or settings.gcs_bucket
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


def delete_avatar(pet_id: str) -> None:
    """Delete all avatar variants for a pet (best-effort)."""
    bucket = _get_bucket()
    for ext in ("jpg", "png", "webp"):
        blob = bucket.blob(f"avatars/{pet_id}.{ext}")
        blob.delete(if_generation_match=None)

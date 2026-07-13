import tempfile
import os
from typing import Optional
from loguru import logger
from app.config import settings


def _get_supabase_client():
    """Lazily initialize Supabase client."""
    from supabase import create_client, Client
    return create_client(settings.supabase_url, settings.supabase_service_key)


async def upload_file_to_storage(
    file_content: bytes,
    storage_path: str,
    content_type: Optional[str] = "application/octet-stream",
) -> str:
    """
    Upload file bytes to Supabase Storage.

    Returns the storage path (used later for download).
    """
    try:
        supabase = _get_supabase_client()

        response = supabase.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=file_content,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "upsert": "true",
            },
        )

        logger.info(f"File uploaded to Supabase Storage: {storage_path}")
        return storage_path

    except Exception as e:
        logger.error(f"Supabase Storage upload failed: {e}")
        raise RuntimeError(f"File upload failed: {str(e)}")


async def download_file_from_storage(storage_path: str) -> str:
    """
    Download a file from Supabase Storage to a local temp file.

    Returns the local file path (caller must clean up).
    """
    try:
        supabase = _get_supabase_client()

        response = supabase.storage.from_(
            settings.supabase_storage_bucket
        ).download(storage_path)

        # Detect extension from path
        ext = storage_path.rsplit(".", 1)[-1] if "." in storage_path else "tmp"

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{ext}"
        ) as tmp:
            tmp.write(response)
            local_path = tmp.name

        logger.info(f"File downloaded from Supabase Storage: {storage_path} → {local_path}")
        return local_path

    except Exception as e:
        logger.error(f"Supabase Storage download failed for {storage_path}: {e}")
        raise RuntimeError(f"File download failed: {str(e)}")


async def delete_file_from_storage(storage_path: str) -> bool:
    """Delete a file from Supabase Storage."""
    try:
        supabase = _get_supabase_client()
        supabase.storage.from_(settings.supabase_storage_bucket).remove([storage_path])
        logger.info(f"Deleted from Supabase Storage: {storage_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete {storage_path}: {e}")
        return False


def get_public_url(storage_path: str) -> str:
    """Get a public URL for a storage file (only works for public buckets)."""
    supabase = _get_supabase_client()
    response = supabase.storage.from_(settings.supabase_storage_bucket).get_public_url(
        storage_path
    )
    return response


async def get_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    """Get a temporary signed URL for private bucket access."""
    try:
        supabase = _get_supabase_client()
        response = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
            storage_path, expires_in
        )
        return response.get("signedURL", "")
    except Exception as e:
        logger.error(f"Failed to create signed URL for {storage_path}: {e}")
        raise
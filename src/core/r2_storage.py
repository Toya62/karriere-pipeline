"""Cloudflare R2 Object Storage Vault for Multi-Tenant Candidate Documents."""

import io
import os
from typing import Any

from src.core.logger import get_logger

logger = get_logger(__name__)

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", os.environ.get("AWS_ACCESS_KEY_ID", ""))
R2_SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY", ""))
R2_BUCKET = os.environ.get("R2_BUCKET_NAME", "karriere-backups")
R2_ENDPOINT = os.environ.get(
    "R2_ENDPOINT_URL",
    f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else "",
)


def is_r2_configured() -> bool:
    """Check if Cloudflare R2 / S3 credentials are configured in the environment."""
    return bool(R2_ACCESS_KEY and R2_SECRET_KEY and (R2_ENDPOINT or os.environ.get("AWS_REGION")))


def _get_s3_client():
    """Build and return a boto3 S3 client configured for Cloudflare R2."""
    if not is_r2_configured():
        return None
    try:
        import boto3
        from botocore.config import Config

        session = boto3.session.Session()
        return session.client(
            service_name="s3",
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY,
            endpoint_url=R2_ENDPOINT if R2_ENDPOINT else None,
            config=Config(signature_version="s3v4"),
        )
    except Exception as exc:
        logger.error(f"Failed to initialize S3 client: {exc}")
        return None


def upload_user_document_to_r2(
    user_id: int,
    category: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> str | None:
    """Upload user file bytes to Cloudflare R2 vault and return the remote storage key."""
    client = _get_s3_client()
    if not client:
        return None

    r2_key = f"vault/{user_id}/{category}/{filename}"
    try:
        client.put_object(
            Bucket=R2_BUCKET,
            Key=r2_key,
            Body=content,
            ContentType=content_type,
        )
        logger.info(f"Uploaded {len(content)} bytes to R2 vault: {r2_key}")
        return r2_key
    except Exception as exc:
        logger.error(f"Failed uploading {r2_key} to R2: {exc}")
        return None


def get_user_document_from_r2(r2_key: str) -> bytes | None:
    """Retrieve raw bytes of an object from Cloudflare R2."""
    client = _get_s3_client()
    if not client:
        return None

    try:
        response = client.get_object(Bucket=R2_BUCKET, Key=r2_key)
        return response["Body"].read()
    except Exception as exc:
        logger.error(f"Failed reading {r2_key} from R2: {exc}")
        return None


def generate_presigned_download_url(r2_key: str, expiration_seconds: int = 3600) -> str | None:
    """Generate a pre-signed GET URL for secure direct client download from Cloudflare R2."""
    client = _get_s3_client()
    if not client:
        return None

    try:
        url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": R2_BUCKET, "Key": r2_key},
            ExpiresIn=expiration_seconds,
        )
        return url
    except Exception as exc:
        logger.error(f"Failed generating presigned URL for {r2_key}: {exc}")
        return None


def delete_user_document_from_r2(r2_key: str) -> bool:
    """Delete an object from Cloudflare R2."""
    client = _get_s3_client()
    if not client:
        return False

    try:
        client.delete_object(Bucket=R2_BUCKET, Key=r2_key)
        logger.info(f"Deleted object {r2_key} from R2")
        return True
    except Exception as exc:
        logger.error(f"Failed deleting {r2_key} from R2: {exc}")
        return False

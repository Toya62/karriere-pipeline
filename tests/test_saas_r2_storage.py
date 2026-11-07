"""Unit tests for Cloudflare R2 object storage vault and fallback handling."""

from src.core.r2_storage import (
    delete_user_document_from_r2,
    generate_presigned_download_url,
    get_user_document_from_r2,
    is_r2_configured,
    upload_user_document_to_r2,
)


def test_r2_configured_or_graceful_skip():
    configured = is_r2_configured()
    if not configured:
        # Graceful no-op when running offline without R2 credentials
        assert upload_user_document_to_r2(1, "transcripts", "test.pdf", b"%PDF-1.4") is None
        assert get_user_document_from_r2("invalid-key") is None
        assert generate_presigned_download_url("invalid-key") is None
        return

    # Real R2 test with configured bucket
    test_pdf = b"%PDF-1.4 unit test sample binary stream for R2 vault"
    r2_key = upload_user_document_to_r2(
        user_id=8888,
        category="job_references",
        filename="ref_8888.pdf",
        content=test_pdf,
    )
    assert r2_key == "vault/8888/job_references/ref_8888.pdf"

    # Read back
    fetched = get_user_document_from_r2(r2_key)
    assert fetched == test_pdf

    # Presigned URL
    url = generate_presigned_download_url(r2_key, expiration_seconds=300)
    assert url is not None
    assert "https://" in url
    assert "X-Amz-Signature" in url

    # Cleanup
    deleted = delete_user_document_from_r2(r2_key)
    assert deleted is True

"""Unit tests for deployment config helpers — no GCP credentials required."""
import pytest

from deployment.config import validate_image_digest


def test_validate_image_digest_accepts_bare_digest():
    digest = "sha256:" + "a" * 64
    assert validate_image_digest(digest) == digest


def test_validate_image_digest_accepts_full_image_ref():
    digest = "europe-west1-docker.pkg.dev/proj/repo@sha256:" + "b" * 64
    assert validate_image_digest(digest) == digest


def test_validate_image_digest_rejects_wrong_length():
    with pytest.raises(ValueError, match="Invalid image digest"):
        validate_image_digest("sha256:" + "a" * 10)


def test_validate_image_digest_rejects_missing_prefix():
    with pytest.raises(ValueError, match="Invalid image digest"):
        validate_image_digest("a" * 64)


def test_validate_image_digest_rejects_uppercase_hex():
    with pytest.raises(ValueError, match="Invalid image digest"):
        validate_image_digest("sha256:" + "A" * 64)

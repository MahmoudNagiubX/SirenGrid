from __future__ import annotations

from pathlib import Path

import pytest

from app.media import (
    AUDIO_MIME_TYPES,
    IMAGE_MIME_TYPES,
    MediaValidationError,
    store_media,
)


def test_audio_is_stored_under_opaque_id_without_exposing_path(tmp_path: Path) -> None:
    result = store_media(
        b"RIFF" + b"synthetic-audio",
        media_kind="audio",
        content_type="audio/wav",
        media_dir=tmp_path,
    )

    assert result.media_id
    assert result.media_reference == f"media:{result.media_id}"
    assert result.media_kind == "audio"
    assert result.mime_type == "audio/wav"
    assert result.size_bytes == 19
    assert result.storage_path is None
    assert len(list(tmp_path.iterdir())) == 1
    assert next(tmp_path.iterdir()).read_bytes() == b"RIFF" + b"synthetic-audio"


def test_image_allowlist_and_audio_allowlist_are_explicit() -> None:
    assert AUDIO_MIME_TYPES == {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/webm",
        "audio/ogg",
    }
    assert IMAGE_MIME_TYPES == {"image/jpeg", "image/png", "image/webp"}


def test_invalid_mime_and_size_are_rejected_before_storage(tmp_path: Path) -> None:
    with pytest.raises(MediaValidationError, match="MIME type"):
        store_media(
            b"x",
            media_kind="audio",
            content_type="video/mp4",
            media_dir=tmp_path,
        )

    with pytest.raises(MediaValidationError, match="too large"):
        store_media(
            b"x" * (15 * 1024 * 1024 + 1),
            media_kind="audio",
            content_type="audio/wav",
            media_dir=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


def test_kind_and_mime_must_match(tmp_path: Path) -> None:
    with pytest.raises(MediaValidationError, match="not permitted"):
        store_media(
            b"image",
            media_kind="image",
            content_type="audio/wav",
            media_dir=tmp_path,
        )

from __future__ import annotations

from pathlib import Path

import pytest

from app.media import (
    AUDIO_MIME_TYPES,
    IMAGE_MIME_TYPES,
    MediaValidationError,
    resolve_media_path,
    store_media,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0"
WAV_BYTES = b"RIFF\x04\x00\x00\x00WAVE"
WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBP"
OGG_BYTES = b"OggS"
WEBM_BYTES = b"\x1a\x45\xdf\xa3"
MP4_BYTES = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 12
MP3_ID3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x00"
MP3_FRAME_BYTES = b"\xff\xfb\x90\x64"


def test_audio_is_stored_under_opaque_id_without_exposing_path(tmp_path: Path) -> None:
    result = store_media(
        WAV_BYTES,
        media_kind="audio",
        content_type="audio/wav",
        media_dir=tmp_path,
    )

    assert result.media_id
    assert result.media_reference == f"media:{result.media_id}"
    assert result.media_kind == "audio"
    assert result.mime_type == "audio/wav"
    assert result.size_bytes == len(WAV_BYTES)
    assert result.storage_path is None
    assert len(list(tmp_path.iterdir())) == 1
    assert next(tmp_path.iterdir()).read_bytes() == WAV_BYTES


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


@pytest.mark.parametrize(
    ("media_kind", "content_type", "content"),
    [
        ("image", "image/png", PNG_BYTES),
        ("image", "image/jpeg", JPEG_BYTES),
        ("image", "image/webp", WEBP_BYTES),
        ("audio", "audio/wav", WAV_BYTES),
        ("audio", "audio/x-wav", WAV_BYTES),
        ("audio", "audio/ogg", OGG_BYTES),
        ("audio", "audio/webm", WEBM_BYTES),
        ("audio", "audio/mpeg", MP3_ID3_BYTES),
        ("audio", "audio/mpeg", MP3_FRAME_BYTES),
        ("audio", "audio/mp4", MP4_BYTES),
    ],
)
def test_supported_media_signatures_are_accepted(
    tmp_path: Path,
    media_kind: str,
    content_type: str,
    content: bytes,
) -> None:
    stored = store_media(
        content,
        media_kind=media_kind,
        content_type=content_type,
        media_dir=tmp_path,
    )

    assert stored.read_bytes() == content


@pytest.mark.parametrize(
    ("media_kind", "content_type", "content"),
    [
        ("image", "image/png", b"PNG synthetic"),
        ("image", "image/jpeg", b"arbitrary jpeg bytes"),
        ("audio", "audio/wav", PNG_BYTES),
        ("image", "image/png", b""),
        ("audio", "audio/wav", b"RIFF"),
    ],
)
def test_missing_mismatched_or_truncated_media_signatures_are_rejected(
    tmp_path: Path,
    media_kind: str,
    content_type: str,
    content: bytes,
) -> None:
    with pytest.raises(MediaValidationError, match="signature"):
        store_media(
            content,
            media_kind=media_kind,
            content_type=content_type,
            media_dir=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


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


def test_media_reference_resolves_only_to_generated_file(tmp_path: Path) -> None:
    stored = store_media(
        WAV_BYTES,
        media_kind="audio",
        content_type="audio/wav",
        media_dir=tmp_path,
    )

    assert resolve_media_path(
        stored.media_reference,
        mime_type="audio/wav",
        media_dir=tmp_path,
    ).read_bytes() == WAV_BYTES
    with pytest.raises(MediaValidationError, match="invalid media reference"):
        resolve_media_path("media:C:\\Windows\\secret", mime_type="audio/wav", media_dir=tmp_path)

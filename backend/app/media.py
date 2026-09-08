"""Bounded opaque media storage for control-room evidence uploads."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from uuid import uuid4

from app.config import settings

AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_MEDIA_ID_PATTERN = re.compile(
    r"^media:(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)


class MediaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredMedia:
    media_id: str
    media_reference: str
    media_kind: str
    mime_type: str
    size_bytes: int
    storage_path: None = None
    _path: Path = field(default=Path(), repr=False, compare=False)

    def public_dict(self) -> dict[str, object]:
        """Return the only shape safe to expose through REST."""
        return {
            "media_id": self.media_id,
            "media_reference": self.media_reference,
            "media_kind": self.media_kind,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
        }

    def read_bytes(self) -> bytes:
        """Read an internally stored object without exposing its path."""
        return self._path.read_bytes()


def _has_media_signature(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if content_type in {"audio/wav", "audio/x-wav"}:
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"
    if content_type == "audio/ogg":
        return content.startswith(b"OggS")
    if content_type == "audio/webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if content_type == "audio/mp4":
        if len(content) < 12 or content[4:8] != b"ftyp":
            return False
        box_size = int.from_bytes(content[:4], byteorder="big")
        return 12 <= box_size <= len(content)
    if content_type == "audio/mpeg":
        if len(content) >= 10 and content.startswith(b"ID3"):
            return True
        if len(content) < 4 or content[0] != 0xFF or content[1] & 0xE0 != 0xE0:
            return False
        version = (content[1] >> 3) & 0x03
        layer = (content[1] >> 1) & 0x03
        bitrate = content[2] >> 4
        sample_rate = (content[2] >> 2) & 0x03
        return version != 1 and layer != 0 and bitrate not in {0, 15} and sample_rate != 3
    return False


def _validate_media(content: bytes, *, media_kind: str, content_type: str) -> str:
    normalized_kind = media_kind.casefold().strip()
    normalized_type = content_type.casefold().strip()
    allowed = AUDIO_MIME_TYPES if normalized_kind == "audio" else IMAGE_MIME_TYPES
    if normalized_kind not in {"audio", "image"}:
        raise MediaValidationError("media kind must be audio or image")
    if normalized_type not in allowed:
        raise MediaValidationError("MIME type is not permitted for this media kind")
    max_bytes = (
        settings.phase06_max_audio_upload_bytes
        if normalized_kind == "audio"
        else settings.phase06_max_image_upload_bytes
    )
    if len(content) > max_bytes:
        raise MediaValidationError("media upload is too large")
    if not _has_media_signature(content, normalized_type):
        raise MediaValidationError("media content does not match the claimed MIME signature")
    return normalized_type


def store_media(
    content: bytes,
    *,
    media_kind: str,
    content_type: str,
    media_dir: Path | None = None,
) -> StoredMedia:
    """Validate and store bytes under a generated UUID filename.

    The configured directory is trusted server configuration; no client value
    participates in the path. The returned public contract intentionally omits
    the internal filesystem path.
    """
    normalized_type = _validate_media(
        content,
        media_kind=media_kind,
        content_type=content_type,
    )
    normalized_kind = media_kind.casefold().strip()
    root = (media_dir or settings.phase06_media_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    media_id = str(uuid4())
    path = root / f"{media_id}{_EXTENSIONS[normalized_type]}"
    path.write_bytes(content)
    return StoredMedia(
        media_id=media_id,
        media_reference=f"media:{media_id}",
        media_kind=normalized_kind,
        mime_type=normalized_type,
        size_bytes=len(content),
        _path=path,
    )


def resolve_media_path(
    media_reference: str,
    *,
    mime_type: str,
    media_dir: Path | None = None,
) -> Path:
    """Resolve an internally stored media reference without accepting a path."""
    match = _MEDIA_ID_PATTERN.fullmatch(media_reference)
    normalized_type = mime_type.casefold().strip()
    if match is None or normalized_type not in _EXTENSIONS:
        raise MediaValidationError("invalid media reference")
    root = (media_dir or settings.phase06_media_dir).resolve()
    path = (root / f"{match.group('id')}{_EXTENSIONS[normalized_type]}").resolve()
    if path.parent != root or not path.is_file():
        raise MediaValidationError("stored media is unavailable")
    return path

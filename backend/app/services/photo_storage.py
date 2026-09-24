"""Replaceable flood-photo storage boundary and safe local implementation."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class InvalidPhoto(ValueError):
    pass


@dataclass(frozen=True)
class StoredPhoto:
    key: str
    content_type: str
    size: int


def detect_image_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


class LocalPhotoStorage:
    """Stores generated object keys below one configured, non-public directory."""

    def __init__(self, root: str, max_bytes: int):
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes

    def save(self, data: bytes) -> StoredPhoto:
        if not data or len(data) > self.max_bytes:
            raise InvalidPhoto("photo is empty or exceeds the configured size limit")
        detected = detect_image_type(data)
        if detected is None:
            raise InvalidPhoto("unsupported image content")
        content_type, extension = detected
        key = f"{uuid4().hex}{extension}"
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)
        destination = self.root / key
        destination.write_bytes(data)
        return StoredPhoto(key=key, content_type=content_type, size=len(data))

    def delete(self, key: str) -> None:
        # Only generated basename keys are accepted, preventing traversal.
        if Path(key).name == key:
            (self.root / key).unlink(missing_ok=True)

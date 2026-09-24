"""Opslag van receptfoto's op schijf; de app serveert ze onder /images/<bestand>."""

import re
import uuid
from pathlib import Path

MAX_IMAGE_BYTES = 8_000_000
URL_PREFIX = "/images/"

# Herken het formaat aan de eerste bytes in plaats van op de opgegeven Content-Type te vertrouwen.
SIGNATURES = [
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
]
CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
NAME_PATTERN = re.compile(r"[0-9a-f]{32}\.(jpg|png|gif|webp)")


def sniff(data):
    """Bestandsextensie van een afbeelding, of None als het geen ondersteunde afbeelding is."""
    for magic, ext, _ in SIGNATURES:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class ImageStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, data):
        """Bewaar afbeeldingsbytes en geef de URL terug waaronder ze te zien zijn."""
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("De afbeelding is te groot (maximaal 8 MB)")
        ext = sniff(data)
        if ext is None:
            raise ValueError("Dit bestand is geen JPEG-, PNG-, GIF- of WebP-afbeelding")
        name = f"{uuid.uuid4().hex}.{ext}"
        (self.directory / name).write_bytes(data)
        return URL_PREFIX + name

    def path_for(self, url):
        """Pad op schijf voor een /images/-URL, of None als de URL niet van ons is."""
        if not isinstance(url, str) or not url.startswith(URL_PREFIX):
            return None
        name = url[len(URL_PREFIX):]
        if not NAME_PATTERN.fullmatch(name):
            return None
        path = self.directory / name
        return path if path.is_file() else None

    def content_type(self, path):
        return CONTENT_TYPES[path.suffix.lstrip(".")]

    def delete(self, url):
        path = self.path_for(url)
        if path:
            path.unlink(missing_ok=True)

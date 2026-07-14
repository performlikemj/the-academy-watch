"""Safeguarding-oriented processing for player showcase photos."""

import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SOURCE_PIXELS = 40_000_000
MAX_LONG_EDGE = 1600
JPEG_QUALITY = 85


class PhotoProcessingError(ValueError):
    """Raised when an uploaded photo cannot be safely normalized."""


def _normalized_rgb(image: Image.Image) -> Image.Image:
    """Apply orientation, flatten transparency, and detach all metadata."""
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def process_photo(raw: bytes) -> tuple[bytes, str]:
    """Normalize JPEG/PNG/WEBP bytes to a metadata-free, bounded JPEG.

    Pillow's decompression-bomb warning is promoted to an error and a stricter
    explicit source-pixel cap is applied before decoding the full image.
    """
    if not isinstance(raw, bytes) or not raw:
        raise PhotoProcessingError("photo is empty")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise PhotoProcessingError("photo must be JPEG, PNG, or WEBP")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_SOURCE_PIXELS:
                    raise PhotoProcessingError("photo dimensions are too large")
                source.seek(0)
                source.load()
                normalized = _normalized_rgb(source)
    except PhotoProcessingError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PhotoProcessingError("photo dimensions are too large") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise PhotoProcessingError("photo is invalid or corrupt") from exc

    if max(normalized.size) > MAX_LONG_EDGE:
        normalized.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)

    # Pillow's JPEG writer falls back to ``Image.info`` for COM comments and
    # other encoder metadata. Clear the decoded image's metadata wholesale so
    # location text outside EXIF cannot survive the re-encode either.
    normalized.info.clear()

    output = BytesIO()
    try:
        # No exif/icc_profile/comment kwargs are supplied: only decoded pixels
        # survive into the approved artifact.
        normalized.save(
            output,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
    except OSError as exc:
        raise PhotoProcessingError("photo could not be encoded") from exc
    finally:
        normalized.close()

    processed = output.getvalue()
    if not processed:
        raise PhotoProcessingError("photo could not be encoded")
    return processed, "image/jpeg"

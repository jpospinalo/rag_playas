"""
Image path relativization and relevance-based image filtering.

Removes images that are too small, duplicated, low-variance (blank/uniform),
or lack semantic context in the surrounding text.
"""

from __future__ import annotations

import hashlib
import logging
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

from .config import (
    IMAGE_CONTEXT_RE,
    IMAGE_CONTEXT_WINDOW,
    IMAGE_FALLBACK_KEEP_ENABLED,
    IMAGE_FALLBACK_MAX_KEEP,
    IMAGE_FALLBACK_MIN_AREA,
    IMAGE_LOW_VARIANCE,
    IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT,
    IMAGE_REQUIRE_SEMANTIC_CONTEXT,
    MIN_IMAGE_PIXELS,
)

logger = logging.getLogger(__name__)


def relativize_image_refs(md_text: str, md_path: Path) -> str:
    """Convert absolute image paths produced by ``save_as_markdown`` to
    relative paths so the markdown stays portable."""
    md_dir = md_path.parent

    def _rel(m: re.Match[str]) -> str:
        alt = m.group(1)
        raw_path = m.group(2)
        try:
            abs_img = Path(raw_path).resolve()
            rel = abs_img.relative_to(md_dir)
            rel_ref = rel.as_posix()
            if not rel_ref.startswith(("./", "../")):
                rel_ref = f"./{rel_ref}"
            return f"![{alt}]({rel_ref})"
        except (ValueError, OSError):
            return m.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _rel, md_text)


def _resolve_image_path(img_ref: str, md_dir: Path) -> Path:
    """Resolve an image reference (potentially URL-encoded or NFC/NFD) to a
    concrete filesystem path."""
    cleaned_ref = img_ref.strip().strip("<>").strip("\"'")
    decoded_ref = unquote(cleaned_ref)
    candidates = [
        decoded_ref,
        unicodedata.normalize("NFC", decoded_ref),
        unicodedata.normalize("NFD", decoded_ref),
    ]

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            candidate_path = (md_dir / candidate).resolve()
        except OSError:
            continue
        if candidate_path.exists() and candidate_path.is_file():
            return candidate_path

    return (md_dir / decoded_ref).resolve()


def filter_images(
    md_text: str,
    md_path: Path,
    min_pixels: int = MIN_IMAGE_PIXELS,
) -> str:
    """Filter out irrelevant images from markdown and delete their files.

    Removal criteria (in order):
    - Smaller than *min_pixels* in both dimensions (``too_small``)
    - Duplicate MD5 hash (``duplicate_hash``)
    - Pixel variance below threshold — blank/uniform image (``low_variance``)
    - No semantic context in surrounding text and area too small
      (``no_semantic_context``)

    When every image would be removed, the fallback logic keeps the largest
    ones (up to ``IMAGE_FALLBACK_MAX_KEEP``) with area >= ``IMAGE_FALLBACK_MIN_AREA``.
    """
    md_dir = md_path.parent
    img_pattern = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

    seen_hashes: set[str] = set()
    reason_counts: Counter[str] = Counter()
    analyzed: list[dict[str, object]] = []

    for match in img_pattern.finditer(md_text):
        img_ref = match.group(1)
        img_file = _resolve_image_path(img_ref, md_dir)

        if not img_file.exists() or not img_file.is_file():
            continue

        try:
            with Image.open(img_file) as img:
                w, h = img.size
                area = w * h
                img_hash = hashlib.md5(img.tobytes()).hexdigest()
                gray = img.convert("L")
                pixels = list(gray.getdata())
        except Exception:
            continue

        remove_reason: str | None = None

        if w < min_pixels and h < min_pixels:
            remove_reason = "too_small"
        elif img_hash in seen_hashes:
            remove_reason = "duplicate_hash"
        else:
            seen_hashes.add(img_hash)

            if len(pixels) > 1 and statistics.variance(pixels) < IMAGE_LOW_VARIANCE:
                remove_reason = "low_variance"

            if remove_reason is None and IMAGE_REQUIRE_SEMANTIC_CONTEXT:
                pos = match.start()
                context = md_text[max(0, pos - IMAGE_CONTEXT_WINDOW) : pos + IMAGE_CONTEXT_WINDOW]
                if (
                    not IMAGE_CONTEXT_RE.search(context)
                    and area < IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT
                ):
                    remove_reason = "no_semantic_context"

        analyzed.append(
            {
                "token": match.group(0),
                "file": img_file,
                "area": area,
                "remove_reason": remove_reason,
            }
        )

    if (
        IMAGE_FALLBACK_KEEP_ENABLED
        and analyzed
        and all(item["remove_reason"] is not None for item in analyzed)
    ):
        fallback_candidates = sorted(
            [item for item in analyzed if int(item["area"]) >= IMAGE_FALLBACK_MIN_AREA],
            key=lambda item: int(item["area"]),
            reverse=True,
        )
        for item in fallback_candidates[: max(1, IMAGE_FALLBACK_MAX_KEEP)]:
            item["remove_reason"] = None
            item["fallback_reason"] = "fallback_keep_large"

    refs_to_remove: list[str] = []
    files_to_remove: list[Path] = []
    kept_count = 0

    for item in analyzed:
        fallback_reason = item.get("fallback_reason")
        if fallback_reason:
            reason_counts[str(fallback_reason)] += 1

        if item["remove_reason"] is None:
            kept_count += 1
            continue

        reason_counts[str(item["remove_reason"])] += 1
        refs_to_remove.append(str(item["token"]))
        files_to_remove.append(item["file"])  # type: ignore[arg-type]

    for img_file in files_to_remove:
        img_file.unlink(missing_ok=True)

    logger.info(
        "Image filtering stats: total=%d kept=%d removed=%d reasons=%s",
        len(analyzed),
        kept_count,
        len(files_to_remove),
        dict(reason_counts),
    )

    for ref in refs_to_remove:
        md_text = md_text.replace(ref, "")

    return md_text

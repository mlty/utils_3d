#!/usr/bin/env python3
"""Extract GLB images into one sibling folder per model."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any, Sequence

from assets_analysis import image_payload, read_glb


MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/ktx2": ".ktx2",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Flat directory containing GLB files.")
    parser.add_argument("--image-dir", default="images", help="Image subdirectory name. Default: images")
    return parser.parse_args(argv)


def safe_stem(value: Any, fallback: str) -> str:
    stem = Path(str(value or "")).stem or fallback
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", stem).strip("._-")
    return stem[:80] or fallback


def image_extension(image: dict[str, Any], payload: bytes) -> str:
    mime_type = image.get("mimeType")
    if isinstance(mime_type, str) and mime_type.lower() in MIME_EXTENSIONS:
        return MIME_EXTENSIONS[mime_type.lower()]
    uri = image.get("uri")
    if isinstance(uri, str):
        suffix = Path(uri.split("?", 1)[0]).suffix.lower()
        if suffix in set(MIME_EXTENSIONS.values()):
            return suffix
    signatures = (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"GIF8", ".gif"),
        (b"BM", ".bmp"),
        (b"\xabKTX 20\xbb\r\n\x1a\n", ".ktx2"),
    )
    for signature, extension in signatures:
        if payload.startswith(signature):
            return extension
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def extract_model(model_path: Path, image_dir_name: str) -> list[dict[str, Any]]:
    gltf, bin_chunks = read_glb(model_path)
    images = gltf.get("images", [])
    if not isinstance(images, list):
        images = []
    output_dir = model_path.parent / model_path.stem / image_dir_name
    rows: list[dict[str, Any]] = []
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            continue
        payload = image_payload(gltf, bin_chunks, model_path, image)
        if payload is None:
            raise ValueError(f"image[{index}] has no readable payload: {model_path}")
        extension = image_extension(image, payload)
        image_name = safe_stem(image.get("name") or image.get("uri"), f"image_{index:03d}")
        output_path = output_dir / f"image_{index:03d}_{image_name}{extension}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        rows.append(
            {
                "model": model_path.name,
                "model_path": str(model_path),
                "image_index": index,
                "image_name": image.get("name", ""),
                "mime_type": image.get("mimeType", ""),
                "byte_size": len(payload),
                "output_path": str(output_path),
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    models = sorted(path for path in args.root.glob("*.glb") if path.is_file())
    all_rows: list[dict[str, Any]] = []
    for index, model_path in enumerate(models, 1):
        rows = extract_model(model_path, args.image_dir)
        all_rows.extend(rows)
        print(f"[{index}/{len(models)}] {model_path.name}: {len(rows)} images")
    fields = ["model", "model_path", "image_index", "image_name", "mime_type", "byte_size", "output_path"]
    with (args.root / "extracted_images_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Done: {len(models)} models, {len(all_rows)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
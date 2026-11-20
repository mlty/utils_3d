#!/usr/bin/env python3
"""Extract/copy FBX texture images into each asset folder's imgs directory."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from pathlib import Path

import bpy


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".tga", ".hdr", ".exr"}


def parse_args() -> argparse.Namespace:
    argv = []
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--texture-dir-name", default="imgs")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for image in list(bpy.data.images):
        bpy.data.images.remove(image)


def safe_stem(value: object, fallback: str) -> str:
    stem = Path(str(value or "")).stem or fallback
    stem = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", stem).strip("._-")
    return stem[:80] or fallback


def unique_path(path: Path, overwrite: bool) -> Path:
    if overwrite or not path.exists():
        return path

    base = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{base}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def image_source_path(image: bpy.types.Image) -> Path | None:
    filepath = image.filepath or image.filepath_raw
    if not filepath:
        return None
    resolved = Path(bpy.path.abspath(filepath))
    if resolved.is_file():
        return resolved
    return None


def output_name(model_path: Path, image: bpy.types.Image, index: int, suffix: str) -> str:
    asset_stem = safe_stem(model_path.stem, "asset")
    image_stem = safe_stem(image.name or image.filepath or image.filepath_raw, f"image_{index:03d}")
    return f"{asset_stem}_image_{index:03d}_{image_stem}{suffix}"


def copy_or_save_image(model_path: Path, image: bpy.types.Image, index: int, output_dir: Path, overwrite: bool) -> str | None:
    if image.size[0] == 0 or image.size[1] == 0:
        return None

    source = image_source_path(image)
    if source and source.suffix.lower() in IMAGE_EXTENSIONS:
        target = unique_path(output_dir / output_name(model_path, image, index, source.suffix.lower()), overwrite)
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return str(target)

    target = unique_path(output_dir / output_name(model_path, image, index, ".png"), overwrite)
    output_dir.mkdir(parents=True, exist_ok=True)
    image.save_render(str(target))
    return str(target)


def extract_fbx(path: Path, root: Path, texture_dir_name: str, overwrite: bool) -> dict[str, object]:
    clear_scene()
    output_dir = path.parent / texture_dir_name
    extracted = []
    errors = []

    try:
        bpy.ops.import_scene.fbx(filepath=str(path))
        for index, image in enumerate(list(bpy.data.images)):
            try:
                saved = copy_or_save_image(path, image, index, output_dir, overwrite)
                if saved:
                    extracted.append(saved)
            except Exception as exc:
                errors.append(f"{image.name}: {exc!r}")
    except Exception as exc:
        errors.append(f"import failed: {exc!r}")

    if errors and extracted:
        status = "partial"
    elif errors:
        status = "failed"
    elif extracted:
        status = "ok"
    else:
        status = "no_images"

    return {
        "folder": path.relative_to(root).parts[0],
        "path": str(path),
        "texture_dir": str(output_dir),
        "status": status,
        "extracted_texture_count": len(extracted),
        "extracted_textures": ";".join(extracted),
        "errors": ";".join(errors),
    }


def main() -> None:
    args = parse_args()
    paths = sorted(args.root.rglob("*.fbx"))
    if args.limit is not None:
        paths = paths[: args.limit]

    rows = [extract_fbx(path, args.root, args.texture_dir_name, args.overwrite) for path in paths]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["folder", "path", "texture_dir", "status", "extracted_texture_count", "extracted_textures", "errors"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} FBX texture rows to {args.report}")


if __name__ == "__main__":
    main()
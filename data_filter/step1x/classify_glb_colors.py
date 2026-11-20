#!/usr/bin/env python3
"""Classify GLB assets by explicit base-color information and sample cases."""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import shutil
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

from assets_analysis import image_payload, read_glb


COMPONENT_FORMATS = {
    5120: ("b", 127.0),
    5121: ("B", 255.0),
    5122: ("h", 32767.0),
    5123: ("H", 65535.0),
    5125: ("I", 4294967295.0),
    5126: ("f", 1.0),
}
TYPE_COMPONENTS = {"VEC3": 3, "VEC4": 4}
GROUP_NAMES = {
    "no_color": "1_no_color",
    "pure_white": "2_pure_white",
    "single_color": "3_single_color",
    "multiple_colors": "4_multiple_colors",
}
CSV_FIELDS = [
    "category",
    "file_name",
    "asset_path",
    "triangle_count",
    "image_count",
    "explicit_factor_count",
    "base_color_texture_count",
    "vertex_color_primitive_count",
    "sampled_color_count",
    "dominant_bucket_ratio",
    "white_ratio",
    "active_color_buckets",
    "note",
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets_csv", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--samples-per-category", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260813)
    return parser.parse_args(argv)


def quantize_color(red: float, green: float, blue: float) -> tuple[int, int, int]:
    return tuple(min(7, max(0, int(channel * 8))) for channel in (red, green, blue))  # type: ignore[return-value]


def add_color(counter: Counter[tuple[int, int, int]], red: float, green: float, blue: float) -> None:
    counter[quantize_color(red, green, blue)] += 1


def texture_sources(gltf: dict[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for index, texture in enumerate(gltf.get("textures", [])):
        if not isinstance(texture, dict):
            continue
        source = texture.get("source")
        extensions = texture.get("extensions", {})
        basisu = extensions.get("KHR_texture_basisu", {}) if isinstance(extensions, dict) else {}
        if isinstance(basisu, dict) and isinstance(basisu.get("source"), int):
            source = basisu["source"]
        if isinstance(source, int):
            result[index] = source
    return result


def sample_texture_colors(
    payload: bytes,
    factor: Sequence[float],
    colors: Counter[tuple[int, int, int]],
) -> tuple[int, int]:
    with Image.open(io.BytesIO(payload)) as image:
        image = image.convert("RGBA")
        image.thumbnail((128, 128), Image.Resampling.BILINEAR)
        sampled = 0
        white = 0
        for red, green, blue, alpha in image.getdata():
            if alpha <= 16:
                continue
            scaled = (
                red / 255.0 * factor[0],
                green / 255.0 * factor[1],
                blue / 255.0 * factor[2],
            )
            add_color(
                colors,
                scaled[0],
                scaled[1],
                scaled[2],
            )
            sampled += 1
            white += min(scaled) >= 0.98
        return sampled, white


def sample_vertex_colors(
    gltf: dict[str, Any],
    bin_chunks: list[bytes],
    accessor_index: int,
    colors: Counter[tuple[int, int, int]],
) -> tuple[int, int]:
    accessors = gltf.get("accessors", [])
    buffer_views = gltf.get("bufferViews", [])
    if not 0 <= accessor_index < len(accessors):
        return 0
    accessor = accessors[accessor_index]
    if not isinstance(accessor, dict) or not isinstance(accessor.get("bufferView"), int):
        return 0
    view = buffer_views[accessor["bufferView"]]
    if not isinstance(view, dict):
        return 0
    component_type = accessor.get("componentType")
    component_info = COMPONENT_FORMATS.get(component_type)
    component_count = TYPE_COMPONENTS.get(accessor.get("type"))
    if component_info is None or component_count is None:
        return 0
    buffer_index = int(view.get("buffer", 0))
    if not 0 <= buffer_index < len(bin_chunks):
        return 0
    value_format, normalizer = component_info
    component_size = struct.calcsize("<" + value_format)
    packed_size = component_size * component_count
    stride = int(view.get("byteStride", packed_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", 0))
    step = max(1, count // 10000)
    sampled = 0
    white = 0
    for item_index in range(0, count, step):
        offset = start + item_index * stride
        values = struct.unpack_from("<" + value_format * component_count, bin_chunks[buffer_index], offset)
        if component_type == 5126:
            red, green, blue = (float(value) for value in values[:3])
        else:
            red, green, blue = (max(0.0, float(value) / normalizer) for value in values[:3])
        add_color(colors, red, green, blue)
        sampled += 1
        white += min(red, green, blue) >= 0.98
    return sampled, white


def classify_asset(row: dict[str, str]) -> dict[str, Any]:
    asset_path = Path(row["asset_path"])
    gltf, bin_chunks = read_glb(asset_path)
    colors: Counter[tuple[int, int, int]] = Counter()
    explicit_factor_count = 0
    base_color_texture_count = 0
    vertex_color_primitive_count = 0
    sampled_color_count = 0
    white_sample_count = 0
    notes: list[str] = []
    sources = texture_sources(gltf)
    images = gltf.get("images", [])

    for material in gltf.get("materials", []):
        if not isinstance(material, dict):
            continue
        pbr = material.get("pbrMetallicRoughness", {})
        if not isinstance(pbr, dict):
            pbr = {}
        factor = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
        if "baseColorFactor" in pbr:
            explicit_factor_count += 1
        texture_info = pbr.get("baseColorTexture")
        if isinstance(texture_info, dict) and isinstance(texture_info.get("index"), int):
            base_color_texture_count += 1
            image_index = sources.get(texture_info["index"])
            if isinstance(image_index, int) and 0 <= image_index < len(images):
                try:
                    payload = image_payload(gltf, bin_chunks, asset_path, images[image_index])
                    if payload:
                        sampled, white = sample_texture_colors(payload, factor, colors)
                        sampled_color_count += sampled
                        white_sample_count += white
                except Exception as error:  # noqa: BLE001 - record unsupported image payloads.
                    notes.append(f"texture_unreadable:{type(error).__name__}")
        elif "baseColorFactor" in pbr:
            add_color(colors, float(factor[0]), float(factor[1]), float(factor[2]))
            sampled_color_count += 1
            white_sample_count += min(float(factor[0]), float(factor[1]), float(factor[2])) >= 0.98

    for mesh in gltf.get("meshes", []):
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives", []):
            attributes = primitive.get("attributes", {}) if isinstance(primitive, dict) else {}
            accessor_index = attributes.get("COLOR_0") if isinstance(attributes, dict) else None
            if isinstance(accessor_index, int):
                vertex_color_primitive_count += 1
                sampled, white = sample_vertex_colors(gltf, bin_chunks, accessor_index, colors)
                sampled_color_count += sampled
                white_sample_count += white

    has_explicit_color = bool(explicit_factor_count or base_color_texture_count or vertex_color_primitive_count)
    if not has_explicit_color:
        category = "no_color"
        dominant_ratio = 0.0
        white_ratio = 0.0
        active_buckets = 0
    elif not colors:
        category = "multiple_colors"
        dominant_ratio = 0.0
        white_ratio = 0.0
        active_buckets = 0
        notes.append("explicit_color_unreadable")
    else:
        total = sum(colors.values())
        dominant_ratio = max(colors.values()) / total
        white_ratio = white_sample_count / sampled_color_count
        active_buckets = sum(count / total >= 0.02 for count in colors.values())
        if white_ratio >= 0.98:
            category = "pure_white"
        elif active_buckets <= 1 or dominant_ratio >= 0.98:
            category = "single_color"
        else:
            category = "multiple_colors"

    return {
        "category": category,
        "file_name": row["file_name"],
        "asset_path": row["asset_path"],
        "triangle_count": row["triangle_count"],
        "image_count": row["image_count"],
        "explicit_factor_count": explicit_factor_count,
        "base_color_texture_count": base_color_texture_count,
        "vertex_color_primitive_count": vertex_color_primitive_count,
        "sampled_color_count": sampled_color_count,
        "dominant_bucket_ratio": round(dominant_ratio, 6),
        "white_ratio": round(white_ratio, 6),
        "active_color_buckets": active_buckets,
        "note": ";".join(sorted(set(notes))),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.out_dir.exists():
        raise SystemExit(f"Output already exists, refusing to overwrite: {args.out_dir}")
    with args.assets_csv.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    results = [classify_asset(row) for row in source_rows]
    args.out_dir.mkdir(parents=True)
    with (args.out_dir / "color_classification.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    rng = random.Random(args.seed)
    manifest: list[dict[str, Any]] = []
    counts = Counter(result["category"] for result in results)
    for category, directory_name in GROUP_NAMES.items():
        candidates = [result for result in results if result["category"] == category]
        selected = rng.sample(candidates, min(args.samples_per_category, len(candidates)))
        category_dir = args.out_dir / directory_name
        category_dir.mkdir()
        for result in selected:
            source = Path(result["asset_path"])
            target = category_dir / source.name
            shutil.copy2(source, target)
            manifest.append({**result, "copied_path": str(target)})
    with (args.out_dir / "sample_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS + ["copied_path"])
        writer.writeheader()
        writer.writerows(manifest)
    summary = {
        "total": len(results),
        "counts": dict(counts),
        "samples_per_category": args.samples_per_category,
        "seed": args.seed,
        "rules": {
            "no_color": "no base-color texture, no vertex color, and no explicit baseColorFactor",
            "pure_white": "at least 98% of sampled colors have R, G, and B each at least 98%",
            "single_color": "one active coarse RGB bucket or at least 98% in the dominant bucket",
            "multiple_colors": "all other assets with explicit color information",
            "active_bucket": "8x8x8 RGB quantization bucket representing at least 2% of samples",
        },
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Analyze GLB assets for low-poly, low-quality, and training-unsuitable candidates."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

DEFAULT_ROOT = Path(r"C:\Users\hongyuanzhu\Data\raw2")
GLB_MAGIC = b"glTF"
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BIN_CHUNK = 0x004E4942
TRIANGLE_MODES = {4, 5, 6}
CSV_FIELDS = [
    "asset_path",
    "file_name",
    "status",
    "file_size_mb",
    "mesh_count",
    "node_count",
    "material_count",
    "primitive_count",
    "vertex_count",
    "triangle_count",
    "image_count",
    "texture_count",
    "max_texture_width",
    "max_texture_height",
    "max_texture_pixels",
    "base_color_texture_count",
    "untextured_material_count",
    "bbox_size_x",
    "bbox_size_y",
    "bbox_size_z",
    "bbox_diagonal",
    "animation_count",
    "skin_count",
    "uses_draco",
    "low_poly",
    "low_quality",
    "not_suitable_for_training",
    "reasons",
    "error",
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class AssetAnalysis:
    asset_path: str
    file_name: str
    status: str
    file_size_mb: float = 0.0
    mesh_count: int = 0
    node_count: int = 0
    material_count: int = 0
    primitive_count: int = 0
    vertex_count: int = 0
    triangle_count: int = 0
    image_count: int = 0
    texture_count: int = 0
    max_texture_width: int = 0
    max_texture_height: int = 0
    max_texture_pixels: int = 0
    base_color_texture_count: int = 0
    untextured_material_count: int = 0
    bbox_size_x: float = 0.0
    bbox_size_y: float = 0.0
    bbox_size_z: float = 0.0
    bbox_diagonal: float = 0.0
    animation_count: int = 0
    skin_count: int = 0
    uses_draco: bool = False
    low_poly: bool = False
    low_quality: bool = False
    not_suitable_for_training: bool = False
    reasons: list[str] | None = None
    error: str = ""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze GLB structure and flag low-poly, low-quality, and training-unsuitable assets."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Root directory to scan for .glb files. Default: {DEFAULT_ROOT}",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum assets to analyze after sorting. Use 0 for all. Default: 0")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent parser workers. Default: 8")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory. Default: logs/assets_analysis_<timestamp>")
    parser.add_argument("--low-poly-triangles", type=int, default=1500, help="Triangle threshold for low-poly flag. Default: 1500")
    parser.add_argument("--very-low-poly-triangles", type=int, default=150, help="Triangle threshold for severe geometry quality flag. Default: 150")
    parser.add_argument("--min-texture-size", type=int, default=256, help="Minimum acceptable max texture width/height when textures exist. Default: 256")
    parser.add_argument("--tiny-file-kb", type=int, default=20, help="File-size threshold for suspicious tiny assets. Default: 20 KB")
    parser.add_argument("--dry-run", action="store_true", help="Only print how many GLB files would be analyzed.")
    return parser.parse_args(argv)


def iter_glb_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.glb") if path.is_file() and not path.name.startswith("."))


def limit_paths(paths: list[Path], limit: int) -> list[Path]:
    return paths[:limit] if limit > 0 else paths


def decode_data_uri(uri: str) -> bytes:
    header, payload = uri.split(",", 1)
    if ";base64" in header:
        return base64.b64decode(payload)
    return payload.encode("utf-8")


def read_glb(path: Path) -> tuple[dict[str, Any], list[bytes]]:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != GLB_MAGIC:
        raise ValueError("not a valid GLB file")

    version, total_length = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise ValueError(f"unsupported GLB version: {version}")
    if total_length > len(data):
        raise ValueError("truncated GLB file")

    gltf_json: dict[str, Any] | None = None
    bin_chunks: list[bytes] = []
    offset = 12
    while offset + 8 <= total_length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == GLB_JSON_CHUNK:
            gltf_json = json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
        elif chunk_type == GLB_BIN_CHUNK:
            bin_chunks.append(chunk)

    if gltf_json is None:
        raise ValueError("GLB has no JSON chunk")
    return gltf_json, bin_chunks


def accessor_count(gltf_json: dict[str, Any], index: Any) -> int:
    if not isinstance(index, int):
        return 0
    accessors = gltf_json.get("accessors", [])
    if index < 0 or index >= len(accessors):
        return 0
    accessor = accessors[index]
    return int(accessor.get("count", 0)) if isinstance(accessor, dict) else 0


def accessor_min_max(gltf_json: dict[str, Any], index: Any) -> tuple[list[float], list[float]] | None:
    if not isinstance(index, int):
        return None
    accessors = gltf_json.get("accessors", [])
    if index < 0 or index >= len(accessors):
        return None
    accessor = accessors[index]
    if not isinstance(accessor, dict):
        return None
    min_value = accessor.get("min")
    max_value = accessor.get("max")
    if not isinstance(min_value, list) or not isinstance(max_value, list) or len(min_value) < 3 or len(max_value) < 3:
        return None
    return [float(value) for value in min_value[:3]], [float(value) for value in max_value[:3]]


def primitive_triangle_count(gltf_json: dict[str, Any], primitive: dict[str, Any]) -> int:
    mode = int(primitive.get("mode", 4))
    if mode not in TRIANGLE_MODES:
        return 0
    indices_count = accessor_count(gltf_json, primitive.get("indices"))
    attributes = primitive.get("attributes") if isinstance(primitive.get("attributes"), dict) else {}
    position_count = accessor_count(gltf_json, attributes.get("POSITION"))
    count = indices_count or position_count
    if mode == 4:
        return count // 3
    return max(count - 2, 0)


def buffer_view_bytes(gltf_json: dict[str, Any], bin_chunks: list[bytes], index: int) -> bytes:
    buffer_views = gltf_json.get("bufferViews", [])
    if index < 0 or index >= len(buffer_views):
        raise ValueError(f"invalid bufferView index: {index}")
    buffer_view = buffer_views[index]
    if not isinstance(buffer_view, dict):
        raise ValueError(f"invalid bufferView value: {index}")
    buffer_index = int(buffer_view.get("buffer", 0))
    if buffer_index < 0 or buffer_index >= len(bin_chunks):
        raise ValueError(f"missing buffer for bufferView index: {index}")
    byte_offset = int(buffer_view.get("byteOffset", 0))
    byte_length = int(buffer_view.get("byteLength", 0))
    return bin_chunks[buffer_index][byte_offset : byte_offset + byte_length]


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", data[16:24])
    return None


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if offset + 7 <= len(data):
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                return width, height
            return None
        offset += segment_length
    return None


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        return struct.unpack("<HH", data[26:30])
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = 1 + (bits & 0x3FFF)
        height = 1 + ((bits >> 14) & 0x3FFF)
        return width, height
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    return png_size(data) or jpeg_size(data) or webp_size(data)


def image_payload(gltf_json: dict[str, Any], bin_chunks: list[bytes], model_path: Path, image: dict[str, Any]) -> bytes | None:
    uri = image.get("uri")
    if isinstance(uri, str) and uri.startswith("data:"):
        return decode_data_uri(uri)
    if isinstance(uri, str):
        source = model_path.parent / uri
        if source.is_file():
            return source.read_bytes()
        return None
    if "bufferView" in image:
        return buffer_view_bytes(gltf_json, bin_chunks, int(image["bufferView"]))
    return None


def has_texture_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any((key.endswith("Texture") and isinstance(item, dict)) or has_texture_reference(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_texture_reference(item) for item in value)
    return False


def material_texture_counts(gltf_json: dict[str, Any]) -> tuple[int, int]:
    materials = gltf_json.get("materials", [])
    base_color_texture_count = 0
    untextured_material_count = 0
    for material in materials:
        if not isinstance(material, dict):
            continue
        pbr = material.get("pbrMetallicRoughness") if isinstance(material.get("pbrMetallicRoughness"), dict) else {}
        has_base_color = isinstance(pbr.get("baseColorTexture"), dict)
        has_any_texture = has_texture_reference(material)
        if has_base_color:
            base_color_texture_count += 1
        if not has_any_texture:
            untextured_material_count += 1
    return base_color_texture_count, untextured_material_count


def uses_draco(gltf_json: dict[str, Any]) -> bool:
    extensions_used = gltf_json.get("extensionsUsed", [])
    if isinstance(extensions_used, list) and "KHR_draco_mesh_compression" in extensions_used:
        return True
    for mesh in gltf_json.get("meshes", []):
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives", []):
            if not isinstance(primitive, dict):
                continue
            extensions = primitive.get("extensions") if isinstance(primitive.get("extensions"), dict) else {}
            if "KHR_draco_mesh_compression" in extensions:
                return True
    return False


def analyze_asset(path: Path, args: argparse.Namespace) -> AssetAnalysis:
    result = AssetAnalysis(
        asset_path=str(path),
        file_name=path.name,
        status="ok",
        file_size_mb=round(path.stat().st_size / (1024 * 1024), 4),
        reasons=[],
    )
    try:
        gltf_json, bin_chunks = read_glb(path)
        meshes = gltf_json.get("meshes", [])
        nodes = gltf_json.get("nodes", [])
        materials = gltf_json.get("materials", [])
        images = gltf_json.get("images", [])
        textures = gltf_json.get("textures", [])
        animations = gltf_json.get("animations", [])
        skins = gltf_json.get("skins", [])

        result.mesh_count = len(meshes) if isinstance(meshes, list) else 0
        result.node_count = len(nodes) if isinstance(nodes, list) else 0
        result.material_count = len(materials) if isinstance(materials, list) else 0
        result.image_count = len(images) if isinstance(images, list) else 0
        result.texture_count = len(textures) if isinstance(textures, list) else 0
        result.animation_count = len(animations) if isinstance(animations, list) else 0
        result.skin_count = len(skins) if isinstance(skins, list) else 0
        result.uses_draco = uses_draco(gltf_json)
        result.base_color_texture_count, result.untextured_material_count = material_texture_counts(gltf_json)

        bbox_min = [math.inf, math.inf, math.inf]
        bbox_max = [-math.inf, -math.inf, -math.inf]
        for mesh in meshes if isinstance(meshes, list) else []:
            if not isinstance(mesh, dict):
                continue
            for primitive in mesh.get("primitives", []):
                if not isinstance(primitive, dict):
                    continue
                result.primitive_count += 1
                result.triangle_count += primitive_triangle_count(gltf_json, primitive)
                attributes = primitive.get("attributes") if isinstance(primitive.get("attributes"), dict) else {}
                result.vertex_count += accessor_count(gltf_json, attributes.get("POSITION"))
                min_max = accessor_min_max(gltf_json, attributes.get("POSITION"))
                if min_max:
                    min_value, max_value = min_max
                    bbox_min = [min(current, value) for current, value in zip(bbox_min, min_value)]
                    bbox_max = [max(current, value) for current, value in zip(bbox_max, max_value)]

        if all(math.isfinite(value) for value in bbox_min + bbox_max):
            result.bbox_size_x = round(bbox_max[0] - bbox_min[0], 6)
            result.bbox_size_y = round(bbox_max[1] - bbox_min[1], 6)
            result.bbox_size_z = round(bbox_max[2] - bbox_min[2], 6)
            result.bbox_diagonal = round(math.sqrt(result.bbox_size_x**2 + result.bbox_size_y**2 + result.bbox_size_z**2), 6)

        for image in images if isinstance(images, list) else []:
            if not isinstance(image, dict):
                continue
            try:
                payload = image_payload(gltf_json, bin_chunks, path, image)
            except Exception:
                payload = None
            if payload:
                size = image_size(payload)
                if size:
                    width, height = size
                    pixels = width * height
                    if pixels > result.max_texture_pixels:
                        result.max_texture_width = width
                        result.max_texture_height = height
                        result.max_texture_pixels = pixels

        apply_quality_flags(result, args)
        return result
    except Exception as error:  # noqa: BLE001 - keep batch analysis going after one bad asset.
        result.status = "failed"
        result.error = str(error)
        result.low_quality = True
        result.not_suitable_for_training = True
        result.reasons = ["parse_failed"]
        return result


def apply_quality_flags(result: AssetAnalysis, args: argparse.Namespace) -> None:
    reasons = result.reasons or []
    file_size_kb = result.file_size_mb * 1024

    if result.mesh_count == 0 or result.primitive_count == 0:
        reasons.append("no_mesh_or_primitives")
    if result.triangle_count <= args.low_poly_triangles:
        result.low_poly = True
        reasons.append(f"low_poly_triangles<={args.low_poly_triangles}")
    if result.triangle_count <= args.very_low_poly_triangles:
        reasons.append(f"very_low_poly_triangles<={args.very_low_poly_triangles}")
    if result.vertex_count <= args.very_low_poly_triangles:
        reasons.append(f"very_low_vertices<={args.very_low_poly_triangles}")
    if result.material_count == 0:
        reasons.append("no_materials")
    if result.image_count == 0 and result.texture_count == 0:
        reasons.append("no_textures")
    if result.image_count > 0 and result.max_texture_pixels == 0:
        reasons.append("texture_dimensions_unknown")
    if result.max_texture_pixels > 0 and min(result.max_texture_width, result.max_texture_height) < args.min_texture_size:
        reasons.append(f"small_texture<{args.min_texture_size}")
    if file_size_kb <= args.tiny_file_kb:
        reasons.append(f"tiny_file<={args.tiny_file_kb}KB")
    if result.bbox_diagonal == 0:
        reasons.append("bbox_missing_or_zero")
    if result.material_count and result.untextured_material_count == result.material_count:
        reasons.append("all_materials_untextured")

    severe = {
        "no_mesh_or_primitives",
        f"very_low_poly_triangles<={args.very_low_poly_triangles}",
        f"very_low_vertices<={args.very_low_poly_triangles}",
        "no_materials",
        "no_textures",
        f"tiny_file<={args.tiny_file_kb}KB",
        "bbox_missing_or_zero",
    }
    result.low_quality = any(reason in severe for reason in reasons) or any(reason.startswith("small_texture") for reason in reasons)
    result.not_suitable_for_training = result.low_quality or (result.low_poly and (result.image_count == 0 or result.material_count == 0))
    result.reasons = reasons


def write_outputs(results: Sequence[AssetAnalysis], out_dir: Path, args: argparse.Namespace) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "assets_analysis.jsonl"
    csv_path = out_dir / "assets_analysis.csv"
    summary_path = out_dir / "summary.json"

    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row["reasons"] = "; ".join(result.reasons or [])
            writer.writerow(row)

    summary = {
        "total": len(results),
        "ok": sum(1 for result in results if result.status == "ok"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "low_poly": sum(1 for result in results if result.low_poly),
        "low_quality": sum(1 for result in results if result.low_quality),
        "not_suitable_for_training": sum(1 for result in results if result.not_suitable_for_training),
        "thresholds": {
            "low_poly_triangles": args.low_poly_triangles,
            "very_low_poly_triangles": args.very_low_poly_triangles,
            "min_texture_size": args.min_texture_size,
            "tiny_file_kb": args.tiny_file_kb,
        },
        "top_reasons": {},
    }
    reason_counts: dict[str, int] = {}
    for result in results:
        for reason in result.reasons or []:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    summary["top_reasons"] = dict(sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:30])
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def progress_bar(done: int, total: int, width: int = 32) -> str:
    if total <= 0:
        return "[" + "." * width + "] 0/0"
    filled = min(width, int(width * done / total))
    return "[" + "#" * filled + "." * (width - filled) + f"] {done}/{total}"


def run_batch(paths: Sequence[Path], args: argparse.Namespace) -> list[AssetAnalysis]:
    results: list[AssetAnalysis] = []
    started = time.time()
    workers = max(args.workers, 1)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(analyze_asset, path, args): path for path in paths}
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            elapsed = max(time.time() - started, 0.001)
            rate = index / elapsed
            print(f"\r{progress_bar(index, len(paths))} rate={rate:.1f}/s last={result.status}", end="", flush=True)
    print()
    return sorted(results, key=lambda item: item.asset_path)


def print_summary(results: Sequence[AssetAnalysis], out_dir: Path) -> None:
    total = len(results)
    low_poly = sum(1 for result in results if result.low_poly)
    low_quality = sum(1 for result in results if result.low_quality)
    not_suitable = sum(1 for result in results if result.not_suitable_for_training)
    failed = sum(1 for result in results if result.status == "failed")
    print(
        f"Done: analyzed {total} assets, failed={failed}, low_poly={low_poly}, "
        f"low_quality={low_quality}, not_suitable_for_training={not_suitable}."
    )
    print(f"outputs: {out_dir}")


def default_out_dir() -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("logs") / f"assets_analysis_{timestamp}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"Root directory does not exist: {root}", file=sys.stderr)
        return 1

    paths = limit_paths(iter_glb_files(root), args.limit)
    if args.dry_run:
        print(f"would analyze {len(paths)} GLB files under {root}")
        return 0
    if not paths:
        print(f"No .glb files found under {root}")
        return 0

    out_dir = args.out_dir or default_out_dir()
    results = run_batch(paths, args)
    write_outputs(results, out_dir, args)
    print_summary(results, out_dir)
    return 1 if any(result.status == "failed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

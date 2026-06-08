#!/usr/bin/env python3
"""Compare base-color texture duplicates across two GLB datasets.

This is a second-layer duplicate detector. It does not prove that two GLB files
are byte-identical; instead, it finds assets whose extracted base-color textures
are identical or visually near-identical across datasets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    Image = importlib.import_module("PIL.Image")
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False


IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".tga",
    ".exr",
    ".hdr",
}

PALETTE_NAME_RE = re.compile(r"(?:color[-_ ]?pallet|color[-_ ]?palette|colour[-_ ]?palette|palette|pallete)", re.IGNORECASE)
NON_COLOR_MAP_RE = re.compile(
    r"(?:^|[_\-. ])(?:n|normal|norm|nrm|nor|bump|height|disp|displacement|roughness|rough|rgh|"
    r"metallic|metalness|specular|spec|gloss|glossiness|ao|occlusion|ambientocclusion|"
    r"orm|rma|mra|arm|mask|opacity|alpha|transmission|thickness|emissive|emission|"
    r"channels?(?:[_\-. ]?[rgba])?|channel(?:[_\-. ]?[rgba])?)(?=$|[_\-. ])",
    re.IGNORECASE,
)
BASE_COLOR_MAP_RE = re.compile(
    r"(?:^|[_\-. ])(?:basecolor|base[-_ ]?color|albedo|diffuse|diff|color|colour|col|bc|d)(?=$|[_\-. ])",
    re.IGNORECASE,
)


@dataclass
class TextureRecord:
    dataset: str
    asset_path: str
    asset_relative_path: str
    asset_status: str
    asset_lod: str
    texture_path: str
    texture_file_name: str
    texture_kind: str
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    file_sha256: str = ""
    pixel_sha256: str = ""
    dhash: str = ""
    error: str = ""


def parse_jsonish(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def texture_map_kind(file_name: str) -> str:
    if PALETTE_NAME_RE.search(file_name):
        return "base_color_palette"
    if BASE_COLOR_MAP_RE.search(Path(file_name).stem):
        return "base_color"
    if NON_COLOR_MAP_RE.search(Path(file_name).stem):
        return "non_color_channel"
    return "base_color_candidate"


def image_files(directory: str) -> List[str]:
    if not directory:
        return []
    root = Path(directory)
    if not root.is_dir():
        return []
    return sorted(str(path) for path in root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS)


def row_texture_paths(row: Dict[str, str], fallback_to_dir: bool) -> List[str]:
    extracted = parse_jsonish(row.get("extracted_textures", ""), [])
    paths = [str(path) for path in extracted if isinstance(path, str) and path]
    if not paths and fallback_to_dir:
        paths = image_files(row.get("texture_extract_dir", ""))
    return sorted(dict.fromkeys(paths))


def load_texture_records(
    assets_csv: Path,
    dataset: str,
    require_asset_exists: bool,
    fallback_to_dir: bool,
    include_palettes: bool,
) -> Tuple[List[TextureRecord], Dict[str, Dict[str, str]], Counter]:
    records: List[TextureRecord] = []
    asset_rows: Dict[str, Dict[str, str]] = {}
    stats: Counter = Counter()
    with assets_csv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stats["asset_rows"] += 1
            asset_path = row.get("path", "")
            if require_asset_exists and (not asset_path or not Path(asset_path).exists()):
                stats["asset_rows_skipped_missing_asset"] += 1
                continue
            asset_rows[asset_path] = row
            texture_paths = row_texture_paths(row, fallback_to_dir)
            if not texture_paths:
                stats["asset_rows_without_textures"] += 1
            for texture_path in texture_paths:
                stats["texture_paths_total"] += 1
                suffix = Path(texture_path).suffix.lower()
                if suffix not in IMAGE_EXTS:
                    stats["texture_paths_skipped_non_image_ext"] += 1
                    continue
                kind = texture_map_kind(Path(texture_path).name)
                if kind == "non_color_channel":
                    stats["texture_paths_skipped_non_color"] += 1
                    continue
                if kind == "base_color_palette" and not include_palettes:
                    stats["texture_paths_skipped_palette"] += 1
                    continue
                records.append(
                    TextureRecord(
                        dataset=dataset,
                        asset_path=asset_path,
                        asset_relative_path=row.get("relative_path", ""),
                        asset_status=row.get("status", ""),
                        asset_lod=row.get("lod", ""),
                        texture_path=texture_path,
                        texture_file_name=Path(texture_path).name,
                        texture_kind=kind,
                    )
                )
    return records, asset_rows, stats


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(2 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pixel_sha256_and_dhash(path: Path, hash_size: int) -> Tuple[int, int, str, str]:
    if not PIL_AVAILABLE or Image is None:
        raise RuntimeError("Pillow is not available")
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        digest = hashlib.sha256()
        digest.update(width.to_bytes(4, "little", signed=False))
        digest.update(height.to_bytes(4, "little", signed=False))
        digest.update(rgba.tobytes())
        gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
    bits = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for column in range(hash_size):
            bits.append(1 if pixels[row_start + column] > pixels[row_start + column + 1] else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    hex_width = math.ceil((hash_size * hash_size) / 4)
    return width, height, digest.hexdigest(), f"{value:0{hex_width}x}"


def inspect_texture(record: TextureRecord, hash_size: int, min_dimension: int) -> TextureRecord:
    path = Path(record.texture_path)
    if not path.exists():
        record.error = "missing_texture"
        return record
    try:
        record.file_size_bytes = path.stat().st_size
        record.file_sha256 = file_sha256(path)
        width, height, pixel_hash, dhash_value = pixel_sha256_and_dhash(path, hash_size)
        record.width = width
        record.height = height
        record.pixel_sha256 = pixel_hash
        record.dhash = dhash_value
        if min(width, height) < min_dimension:
            record.error = f"too_small_{width}x{height}"
    except Exception as exc:
        record.error = str(exc)
    return record


def inspect_records(records: Sequence[TextureRecord], workers: int, hash_size: int, min_dimension: int, progress_every: int) -> None:
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(inspect_texture, record, hash_size, min_dimension) for record in records]
        for future in as_completed(futures):
            future.result()
            completed += 1
            if progress_every > 0 and completed % progress_every == 0:
                print(f"texture hash progress: {completed}/{len(records)}")


def hamming_hex(left: str, right: str) -> int:
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def dimension_ratio(left: TextureRecord, right: TextureRecord) -> float:
    if left.width <= 0 or left.height <= 0 or right.width <= 0 or right.height <= 0:
        return 0.0
    width_ratio = min(left.width, right.width) / max(left.width, right.width)
    height_ratio = min(left.height, right.height) / max(left.height, right.height)
    return min(width_ratio, height_ratio)


def asset_texture_counts(records: Sequence[TextureRecord]) -> Dict[str, int]:
    counts: Dict[str, Set[str]] = defaultdict(set)
    for record in records:
        if not record.error and record.pixel_sha256:
            counts[record.asset_path].add(record.texture_path)
    return {path: len(values) for path, values in counts.items()}


def write_manifest(path: Path, records: Sequence[TextureRecord]) -> None:
    fieldnames = [
        "dataset",
        "asset_path",
        "asset_relative_path",
        "asset_status",
        "asset_lod",
        "texture_path",
        "texture_file_name",
        "texture_kind",
        "width",
        "height",
        "file_size_bytes",
        "file_sha256",
        "pixel_sha256",
        "dhash",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: getattr(record, field) for field in fieldnames})


def write_rows(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_candidate_strength_path_files(out_dir: Path, candidate_rows: Sequence[Dict[str, Any]], left_name: str, right_name: str) -> Dict[str, int]:
    split_dir = out_dir / "candidate_pairs_by_strength"
    split_dir.mkdir(parents=True, exist_ok=True)
    strength_order = [
        "strong_exact_basecolor",
        "medium_exact_basecolor",
        "medium_perceptual_basecolor",
        "weak_perceptual_basecolor",
    ]
    rows_by_strength: Dict[str, List[Dict[str, Any]]] = {strength: [] for strength in strength_order}
    for row in candidate_rows:
        rows_by_strength.setdefault(str(row.get("candidate_strength", "unknown")), []).append(row)

    counts: Dict[str, int] = {}
    for strength, rows in rows_by_strength.items():
        csv_path = split_dir / f"{strength}_glb_paths.csv"
        txt_path = split_dir / f"{strength}_glb_paths.txt"
        counts[strength] = len(rows)
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["A_glb_path", "B_glb_path"])
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "A_glb_path": row[f"{left_name}_asset_path"],
                        "B_glb_path": row[f"{right_name}_asset_path"],
                    }
                )
        with txt_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(f"{row[f'{left_name}_asset_path']}\t{row[f'{right_name}_asset_path']}\n")
    return counts


def aggregate_asset_pairs(
    texture_pairs: Sequence[Dict[str, Any]],
    left_counts: Dict[str, int],
    right_counts: Dict[str, int],
    left_name: str,
    right_name: str,
    match_key: str,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for pair in texture_pairs:
        key = (pair[f"{left_name}_asset_path"], pair[f"{right_name}_asset_path"])
        item = grouped.setdefault(
            key,
            {
                f"{left_name}_asset_path": key[0],
                f"{left_name}_asset_relative_path": pair.get(f"{left_name}_asset_relative_path", ""),
                f"{right_name}_asset_path": key[1],
                f"{right_name}_asset_relative_path": pair.get(f"{right_name}_asset_relative_path", ""),
                f"{left_name}_basecolor_count": left_counts.get(key[0], 0),
                f"{right_name}_basecolor_count": right_counts.get(key[1], 0),
                "matched_texture_pair_count": 0,
                "matched_left_texture_count": 0,
                "matched_right_texture_count": 0,
                "matched_hash_count": 0,
                "best_hamming_distance": "",
                "matched_texture_examples": [],
            },
        )
        item["matched_texture_pair_count"] += 1
        item.setdefault("_left_textures", set()).add(pair[f"{left_name}_texture_path"])
        item.setdefault("_right_textures", set()).add(pair[f"{right_name}_texture_path"])
        item.setdefault("_hashes", set()).add(pair.get(match_key, ""))
        if "hamming_distance" in pair:
            distance = int(pair["hamming_distance"])
            best = item["best_hamming_distance"]
            item["best_hamming_distance"] = distance if best == "" else min(int(best), distance)
        if len(item["matched_texture_examples"]) < 5:
            item["matched_texture_examples"].append(
                f"{Path(pair[f'{left_name}_texture_path']).name} <=> {Path(pair[f'{right_name}_texture_path']).name}"
            )
    rows = []
    for item in grouped.values():
        left_matched = len(item.pop("_left_textures", set()))
        right_matched = len(item.pop("_right_textures", set()))
        hash_count = len({value for value in item.pop("_hashes", set()) if value})
        item["matched_left_texture_count"] = left_matched
        item["matched_right_texture_count"] = right_matched
        item["matched_hash_count"] = hash_count
        left_total = max(int(item[f"{left_name}_basecolor_count"]), 1)
        right_total = max(int(item[f"{right_name}_basecolor_count"]), 1)
        item["left_match_ratio"] = round(min(left_matched / left_total, 1.0), 4)
        item["right_match_ratio"] = round(min(right_matched / right_total, 1.0), 4)
        item["min_match_ratio"] = round(min(item["left_match_ratio"], item["right_match_ratio"]), 4)
        item["jaccard_like_score"] = round((left_matched + right_matched) / max(left_total + right_total, 1), 4)
        item["matched_texture_examples"] = json.dumps(item["matched_texture_examples"], ensure_ascii=False)
        rows.append(item)
    rows.sort(key=lambda row: (-row["min_match_ratio"], -row["matched_hash_count"], row[f"{left_name}_asset_relative_path"], row[f"{right_name}_asset_relative_path"]))
    return rows


def exact_texture_pairs(
    left_records: Sequence[TextureRecord],
    right_records: Sequence[TextureRecord],
    left_name: str,
    right_name: str,
    max_hash_asset_count: int,
) -> Tuple[List[Dict[str, Any]], Counter]:
    grouped: Dict[str, Dict[str, List[TextureRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in list(left_records) + list(right_records):
        if record.error or not record.pixel_sha256:
            continue
        grouped[record.pixel_sha256][record.dataset].append(record)

    rows: List[Dict[str, Any]] = []
    stats: Counter = Counter()
    for pixel_hash, by_dataset in grouped.items():
        left_group = by_dataset.get(left_name, [])
        right_group = by_dataset.get(right_name, [])
        if not left_group or not right_group:
            continue
        left_assets = {record.asset_path for record in left_group}
        right_assets = {record.asset_path for record in right_group}
        if max_hash_asset_count > 0 and (len(left_assets) > max_hash_asset_count or len(right_assets) > max_hash_asset_count):
            stats["skipped_common_pixel_hash_groups"] += 1
            continue
        stats["cross_pixel_hash_groups"] += 1
        for left in left_group:
            for right in right_group:
                rows.append(
                    {
                        "pixel_sha256": pixel_hash,
                        "width": left.width,
                        "height": left.height,
                        f"{left_name}_asset_path": left.asset_path,
                        f"{left_name}_asset_relative_path": left.asset_relative_path,
                        f"{left_name}_texture_path": left.texture_path,
                        f"{left_name}_texture_file_name": left.texture_file_name,
                        f"{right_name}_asset_path": right.asset_path,
                        f"{right_name}_asset_relative_path": right.asset_relative_path,
                        f"{right_name}_texture_path": right.texture_path,
                        f"{right_name}_texture_file_name": right.texture_file_name,
                    }
                )
    return rows, stats


def perceptual_texture_pairs(
    left_records: Sequence[TextureRecord],
    right_records: Sequence[TextureRecord],
    left_name: str,
    right_name: str,
    dhash_distance: int,
    min_dimension_ratio: float,
    max_bucket_size: int,
    max_pairs: int,
) -> Tuple[List[Dict[str, Any]], Counter]:
    valid_right = [record for record in right_records if not record.error and record.dhash]
    buckets: Dict[Tuple[int, str], List[TextureRecord]] = defaultdict(list)
    for record in valid_right:
        for index in range(4):
            buckets[(index, record.dhash[index * 4 : (index + 1) * 4])].append(record)

    rows: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()
    stats: Counter = Counter()
    for left in left_records:
        if left.error or not left.dhash:
            continue
        candidates: Dict[str, TextureRecord] = {}
        for index in range(4):
            bucket = buckets.get((index, left.dhash[index * 4 : (index + 1) * 4]), [])
            if max_bucket_size > 0 and len(bucket) > max_bucket_size:
                stats["skipped_large_lsh_buckets"] += 1
                continue
            for right in bucket:
                candidates[right.texture_path] = right
        for right in candidates.values():
            key = (left.texture_path, right.texture_path)
            if key in seen:
                continue
            seen.add(key)
            dim_ratio = dimension_ratio(left, right)
            if dim_ratio < min_dimension_ratio:
                continue
            distance = hamming_hex(left.dhash, right.dhash)
            if distance > dhash_distance:
                continue
            rows.append(
                {
                    "hamming_distance": distance,
                    "dimension_ratio": round(dim_ratio, 4),
                    f"{left_name}_dhash": left.dhash,
                    f"{right_name}_dhash": right.dhash,
                    f"{left_name}_asset_path": left.asset_path,
                    f"{left_name}_asset_relative_path": left.asset_relative_path,
                    f"{left_name}_texture_path": left.texture_path,
                    f"{left_name}_texture_file_name": left.texture_file_name,
                    f"{right_name}_asset_path": right.asset_path,
                    f"{right_name}_asset_relative_path": right.asset_relative_path,
                    f"{right_name}_texture_path": right.texture_path,
                    f"{right_name}_texture_file_name": right.texture_file_name,
                }
            )
            if max_pairs > 0 and len(rows) >= max_pairs:
                stats["stopped_at_max_pairs"] = max_pairs
                rows.sort(key=lambda row: (row["hamming_distance"], -row["dimension_ratio"]))
                return rows, stats
    rows.sort(key=lambda row: (row["hamming_distance"], -row["dimension_ratio"], row[f"{left_name}_asset_relative_path"]))
    return rows, stats


def classify_candidate(row: Dict[str, Any], exact: bool) -> str:
    min_ratio = float(row.get("min_match_ratio") or 0)
    matched = int(row.get("matched_hash_count") or row.get("matched_texture_pair_count") or 0)
    if exact and (min_ratio >= 0.8 or matched >= 2):
        return "strong_exact_basecolor"
    if exact:
        return "medium_exact_basecolor"
    if min_ratio >= 0.8:
        return "medium_perceptual_basecolor"
    return "weak_perceptual_basecolor"


def merge_candidate_asset_pairs(
    exact_rows: Sequence[Dict[str, Any]],
    perceptual_rows: Sequence[Dict[str, Any]],
    left_name: str,
    right_name: str,
) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for source, rows in (("exact", exact_rows), ("perceptual", perceptual_rows)):
        for row in rows:
            key = (row[f"{left_name}_asset_path"], row[f"{right_name}_asset_path"])
            item = merged.setdefault(
                key,
                {
                    f"{left_name}_asset_path": key[0],
                    f"{left_name}_asset_relative_path": row.get(f"{left_name}_asset_relative_path", ""),
                    f"{right_name}_asset_path": key[1],
                    f"{right_name}_asset_relative_path": row.get(f"{right_name}_asset_relative_path", ""),
                    "exact_matched_hash_count": 0,
                    "exact_min_match_ratio": 0.0,
                    "perceptual_matched_texture_pair_count": 0,
                    "perceptual_min_match_ratio": 0.0,
                    "best_hamming_distance": "",
                    "candidate_strength": "",
                },
            )
            if source == "exact":
                item["exact_matched_hash_count"] = max(item["exact_matched_hash_count"], int(row.get("matched_hash_count") or 0))
                item["exact_min_match_ratio"] = max(item["exact_min_match_ratio"], float(row.get("min_match_ratio") or 0))
            else:
                item["perceptual_matched_texture_pair_count"] = max(
                    item["perceptual_matched_texture_pair_count"], int(row.get("matched_texture_pair_count") or 0)
                )
                item["perceptual_min_match_ratio"] = max(item["perceptual_min_match_ratio"], float(row.get("min_match_ratio") or 0))
                best = row.get("best_hamming_distance", "")
                if best != "":
                    item["best_hamming_distance"] = best if item["best_hamming_distance"] == "" else min(int(item["best_hamming_distance"]), int(best))
    for item in merged.values():
        if item["exact_matched_hash_count"]:
            item["candidate_strength"] = classify_candidate({"min_match_ratio": item["exact_min_match_ratio"], "matched_hash_count": item["exact_matched_hash_count"]}, True)
        else:
            item["candidate_strength"] = classify_candidate(
                {"min_match_ratio": item["perceptual_min_match_ratio"], "matched_texture_pair_count": item["perceptual_matched_texture_pair_count"]},
                False,
            )
    strength_order = {
        "strong_exact_basecolor": 0,
        "medium_exact_basecolor": 1,
        "medium_perceptual_basecolor": 2,
        "weak_perceptual_basecolor": 3,
    }
    rows = list(merged.values())
    rows.sort(
        key=lambda row: (
            strength_order.get(row["candidate_strength"], 99),
            -row["exact_min_match_ratio"],
            -row["perceptual_min_match_ratio"],
            row[f"{left_name}_asset_relative_path"],
        )
    )
    return rows


def render_summary(summary: Dict[str, Any], out_dir: Path, left_name: str, right_name: str) -> None:
    lines = ["# Cross Dataset Base Color Duplicate Report", ""]
    for key, value in summary.items():
        if key in {"candidate_strength_counts"}:
            continue
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Candidate Strength Counts", ""])
    for key, value in summary.get("candidate_strength_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `strong_exact_basecolor`: base-color pixel hashes match with high coverage or multiple matching textures.",
            "- `medium_exact_basecolor`: at least one exact base-color pixel hash is shared; useful candidate, not final proof.",
            "- `medium_perceptual_basecolor` / `weak_perceptual_basecolor`: visually similar dHash candidates; inspect with geometry/normal renders before rejecting.",
            "",
            "## Output Files",
            "",
            "- `basecolor_manifest.csv`: all inspected base-color texture records.",
            "- `exact_basecolor_texture_pairs.csv`: exact decoded-pixel texture matches.",
            "- `exact_basecolor_asset_pairs.csv`: asset pairs aggregated from exact texture matches.",
            "- `perceptual_basecolor_texture_pairs.csv`: dHash-similar texture matches.",
            "- `perceptual_basecolor_asset_pairs.csv`: asset pairs aggregated from dHash matches.",
            "- `candidate_duplicate_asset_pairs.csv`: merged asset-level candidate list.",
            "",
        ]
    )
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def compare(args: argparse.Namespace) -> Dict[str, Any]:
    start = time.time()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    left_name = args.left_name
    right_name = args.right_name

    left_records, _, left_load_stats = load_texture_records(
        Path(args.left_assets_csv), left_name, args.require_asset_exists, args.fallback_to_dir, args.include_palettes
    )
    right_records, _, right_load_stats = load_texture_records(
        Path(args.right_assets_csv), right_name, args.require_asset_exists, args.fallback_to_dir, args.include_palettes
    )
    all_records = left_records + right_records
    print(f"loaded basecolor candidates: {left_name}={len(left_records)}, {right_name}={len(right_records)}")
    inspect_records(all_records, args.workers, args.hash_size, args.min_dimension, args.progress_every)

    valid_left = [record for record in left_records if not record.error and record.pixel_sha256]
    valid_right = [record for record in right_records if not record.error and record.pixel_sha256]
    left_counts = asset_texture_counts(valid_left)
    right_counts = asset_texture_counts(valid_right)

    exact_pairs, exact_stats = exact_texture_pairs(valid_left, valid_right, left_name, right_name, args.max_hash_asset_count)
    exact_asset_rows = aggregate_asset_pairs(exact_pairs, left_counts, right_counts, left_name, right_name, "pixel_sha256")

    perceptual_pairs, perceptual_stats = perceptual_texture_pairs(
        valid_left,
        valid_right,
        left_name,
        right_name,
        args.dhash_distance,
        args.min_dimension_ratio,
        args.max_lsh_bucket_size,
        args.max_perceptual_texture_pairs,
    )
    perceptual_asset_rows = aggregate_asset_pairs(perceptual_pairs, left_counts, right_counts, left_name, right_name, f"{left_name}_dhash")
    candidate_rows = merge_candidate_asset_pairs(exact_asset_rows, perceptual_asset_rows, left_name, right_name)

    write_manifest(out_dir / "basecolor_manifest.csv", all_records)
    exact_texture_fields = [
        "pixel_sha256",
        "width",
        "height",
        f"{left_name}_asset_path",
        f"{left_name}_asset_relative_path",
        f"{left_name}_texture_path",
        f"{left_name}_texture_file_name",
        f"{right_name}_asset_path",
        f"{right_name}_asset_relative_path",
        f"{right_name}_texture_path",
        f"{right_name}_texture_file_name",
    ]
    write_rows(out_dir / "exact_basecolor_texture_pairs.csv", exact_pairs, exact_texture_fields)

    asset_fields = [
        f"{left_name}_asset_path",
        f"{left_name}_asset_relative_path",
        f"{right_name}_asset_path",
        f"{right_name}_asset_relative_path",
        f"{left_name}_basecolor_count",
        f"{right_name}_basecolor_count",
        "matched_texture_pair_count",
        "matched_left_texture_count",
        "matched_right_texture_count",
        "matched_hash_count",
        "best_hamming_distance",
        "left_match_ratio",
        "right_match_ratio",
        "min_match_ratio",
        "jaccard_like_score",
        "matched_texture_examples",
    ]
    write_rows(out_dir / "exact_basecolor_asset_pairs.csv", exact_asset_rows, asset_fields)

    perceptual_texture_fields = [
        "hamming_distance",
        "dimension_ratio",
        f"{left_name}_dhash",
        f"{right_name}_dhash",
        f"{left_name}_asset_path",
        f"{left_name}_asset_relative_path",
        f"{left_name}_texture_path",
        f"{left_name}_texture_file_name",
        f"{right_name}_asset_path",
        f"{right_name}_asset_relative_path",
        f"{right_name}_texture_path",
        f"{right_name}_texture_file_name",
    ]
    write_rows(out_dir / "perceptual_basecolor_texture_pairs.csv", perceptual_pairs, perceptual_texture_fields)
    write_rows(out_dir / "perceptual_basecolor_asset_pairs.csv", perceptual_asset_rows, asset_fields)

    candidate_fields = [
        f"{left_name}_asset_path",
        f"{left_name}_asset_relative_path",
        f"{right_name}_asset_path",
        f"{right_name}_asset_relative_path",
        "candidate_strength",
        "exact_matched_hash_count",
        "exact_min_match_ratio",
        "perceptual_matched_texture_pair_count",
        "perceptual_min_match_ratio",
        "best_hamming_distance",
    ]
    write_rows(out_dir / "candidate_duplicate_asset_pairs.csv", candidate_rows, candidate_fields)
    candidate_path_file_counts = write_candidate_strength_path_files(out_dir, candidate_rows, left_name, right_name)

    strength_counts = Counter(row["candidate_strength"] for row in candidate_rows)
    summary: Dict[str, Any] = {
        "left_name": left_name,
        "right_name": right_name,
        "left_assets_csv": str(Path(args.left_assets_csv).resolve()),
        "right_assets_csv": str(Path(args.right_assets_csv).resolve()),
        "require_asset_exists": args.require_asset_exists,
        f"{left_name}_loaded_basecolor_texture_count": len(left_records),
        f"{right_name}_loaded_basecolor_texture_count": len(right_records),
        f"{left_name}_valid_basecolor_texture_count": len(valid_left),
        f"{right_name}_valid_basecolor_texture_count": len(valid_right),
        f"{left_name}_asset_with_valid_basecolor_count": len(left_counts),
        f"{right_name}_asset_with_valid_basecolor_count": len(right_counts),
        f"{left_name}_load_stats": dict(left_load_stats),
        f"{right_name}_load_stats": dict(right_load_stats),
        "exact_texture_pair_count": len(exact_pairs),
        "exact_asset_pair_count": len(exact_asset_rows),
        "perceptual_texture_pair_count": len(perceptual_pairs),
        "perceptual_asset_pair_count": len(perceptual_asset_rows),
        "candidate_asset_pair_count": len(candidate_rows),
        "candidate_strength_counts": dict(strength_counts.most_common()),
        "candidate_strength_path_file_counts": candidate_path_file_counts,
        "exact_stats": dict(exact_stats),
        "perceptual_stats": dict(perceptual_stats),
        "dhash_distance": args.dhash_distance,
        "min_dimension_ratio": args.min_dimension_ratio,
        "min_dimension": args.min_dimension,
        "max_hash_asset_count": args.max_hash_asset_count,
        "include_palettes": args.include_palettes,
        "elapsed_sec": round(time.time() - start, 3),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_summary(summary, out_dir, left_name, right_name)
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-assets-csv", required=True)
    parser.add_argument("--right-assets-csv", required=True)
    parser.add_argument("--left-name", default="left")
    parser.add_argument("--right-name", default="right")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--hash-size", type=int, default=8, help="dHash size; 8 means 64-bit hash")
    parser.add_argument("--dhash-distance", type=int, default=4)
    parser.add_argument("--min-dimension-ratio", type=float, default=0.85)
    parser.add_argument("--min-dimension", type=int, default=64)
    parser.add_argument("--max-hash-asset-count", type=int, default=20, help="Skip exact texture hashes shared by too many assets in either dataset; 0 disables")
    parser.add_argument("--max-lsh-bucket-size", type=int, default=2000, help="Skip dHash LSH buckets that are too broad; 0 disables")
    parser.add_argument("--max-perceptual-texture-pairs", type=int, default=200000, help="Safety cap for dHash texture pairs; 0 disables")
    parser.add_argument("--include-palettes", action="store_true")
    parser.add_argument("--no-require-asset-exists", dest="require_asset_exists", action="store_false")
    parser.set_defaults(require_asset_exists=True)
    parser.add_argument("--fallback-to-dir", action="store_true")
    parser.add_argument("--progress-every", type=int, default=5000)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = compare(args)
    print("===== cross dataset basecolor duplicate report =====")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"report_dir: {Path(args.out_dir).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

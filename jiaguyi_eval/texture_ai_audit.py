#!/usr/bin/env python3
"""Audit extracted texture images for AI/invalid texture signals.

The checks are intentionally conservative enough for triage: palette/color-chart
textures are treated as hard texture problems, while fragmented UV atlases and
temporary/generic texture filenames are treated as AI-review signals.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    Image = importlib.import_module("PIL.Image")
    ImageFilter = importlib.import_module("PIL.ImageFilter")
    ImageStat = importlib.import_module("PIL.ImageStat")
    PIL_AVAILABLE = True
except Exception:
    Image = None
    ImageFilter = None
    ImageStat = None
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
TEMP_NAME_RE = re.compile(r"(?:sketchfabtemp|temptexture|tmptexture|generated|aigc|meshy|tripo)", re.IGNORECASE)
GENERIC_IMAGE_RE = re.compile(r"(?:^|[_\- ])image[_\- ]?0(?:[_\- ]?0)?(?:\D|$)", re.IGNORECASE)
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


ASSET_FIELDS = [
    "severity",
    "texture_issue_types",
    "flagged_texture_count",
    "texture_count_checked",
    "texture_count_total",
    "skipped_non_color_texture_count",
    "max_edge_density",
    "max_dark_ratio",
    "max_bright_ratio",
    "min_top_color_ratio",
    "path",
    "relative_path",
    "folder",
    "status",
    "lod",
    "face_count",
    "image_count",
    "texture_count",
    "extracted_texture_count",
    "ai_score",
    "ai_risk",
    "flagged_textures",
]

IMAGE_FIELDS = [
    "severity",
    "issue_types",
    "image_path",
    "file_name",
    "texture_map_kind",
    "path",
    "relative_path",
    "folder",
    "width",
    "height",
    "aspect_ratio",
    "dark_ratio",
    "bright_ratio",
    "transparent_ratio",
    "edge_density",
    "edge_mean",
    "gray_entropy",
    "top_color_ratio",
    "quantized_color_count",
]

FINDING_FIELDS = ["severity", "issue", "path", "relative_path", "folder", "image_path", "details"]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_jsonish(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed


def entropy_from_histogram(histogram: Sequence[int]) -> float:
    total = sum(histogram)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in histogram:
        if count:
            probability = count / total
            entropy -= probability * math.log(probability, 2)
    return entropy


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


def texture_map_kind(file_name: str) -> str:
    if PALETTE_NAME_RE.search(file_name):
        return "base_color_palette"
    if BASE_COLOR_MAP_RE.search(Path(file_name).stem):
        return "base_color"
    if NON_COLOR_MAP_RE.search(Path(file_name).stem):
        return "non_color_channel"
    return "base_color_candidate"


def filter_texture_paths(paths: Sequence[str], args: argparse.Namespace) -> List[str]:
    if args.texture_map_scope == "all":
        return list(paths)
    return [path for path in paths if texture_map_kind(Path(path).name) != "non_color_channel"]


def classify_name(file_name: str) -> List[str]:
    flags: List[str] = []
    if PALETTE_NAME_RE.search(file_name):
        flags.append("filename_palette_marker")
    if TEMP_NAME_RE.search(file_name):
        flags.append("filename_temp_or_ai_marker")
    if GENERIC_IMAGE_RE.search(file_name):
        flags.append("filename_generic_image_0")
    return flags


def inspect_texture_image(image_path: str, thumb_size: int, edge_threshold: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "image_path": image_path,
        "file_name": Path(image_path).name,
        "texture_map_kind": texture_map_kind(Path(image_path).name),
        "readable": False,
        "name_flags": classify_name(Path(image_path).name),
    }
    if not PIL_AVAILABLE or Image is None or ImageFilter is None or ImageStat is None:
        result["error"] = "Pillow is not available"
        return result
    if not os.path.exists(image_path):
        result["error"] = "missing image"
        return result
    try:
        with Image.open(image_path) as image:
            original_width, original_height = image.size
            rgba = image.convert("RGBA")
            rgba.thumbnail((thumb_size, thumb_size))
            rgb = rgba.convert("RGB")
            gray = rgb.convert("L")
    except Exception as exc:
        result["error"] = str(exc)
        return result

    width, height = rgb.size
    total = max(width * height, 1)
    gray_pixels = list(gray.getdata())
    alpha_pixels = list(rgba.getchannel("A").getdata())
    dark_ratio = sum(1 for value in gray_pixels if value < 24) / total
    bright_ratio = sum(1 for value in gray_pixels if value > 235) / total
    transparent_ratio = sum(1 for value in alpha_pixels if value < 8) / total

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_histogram = edges.histogram()
    edge_density = sum(count for value, count in enumerate(edge_histogram) if value > edge_threshold) / max(sum(edge_histogram), 1)
    edge_mean = float(ImageStat.Stat(edges).mean[0])
    gray_entropy = entropy_from_histogram(gray.histogram())

    try:
        quantized = rgb.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
        colors = quantized.getcolors(maxcolors=1000000) or []
        top_color_ratio = max((count for count, _ in colors), default=0) / total
        quantized_color_count = len(colors)
    except Exception:
        top_color_ratio = 0.0
        quantized_color_count = 0

    result.update(
        {
            "readable": True,
            "width": original_width,
            "height": original_height,
            "aspect_ratio": round(original_width / original_height, 6) if original_height else 0.0,
            "dark_ratio": round(dark_ratio, 6),
            "bright_ratio": round(bright_ratio, 6),
            "transparent_ratio": round(transparent_ratio, 6),
            "edge_density": round(edge_density, 6),
            "edge_mean": round(edge_mean, 6),
            "gray_entropy": round(gray_entropy, 6),
            "top_color_ratio": round(top_color_ratio, 6),
            "quantized_color_count": quantized_color_count,
        }
    )
    return result


def classify_texture(metrics: Dict[str, Any], args: argparse.Namespace) -> Tuple[str, List[str]]:
    issue_types = list(metrics.get("name_flags", []))
    if not metrics.get("readable"):
        return "texture_problem", ["unreadable_texture"] + issue_types

    file_name = str(metrics.get("file_name", ""))
    dark_ratio = safe_float(metrics.get("dark_ratio"))
    bright_ratio = safe_float(metrics.get("bright_ratio"))
    transparent_ratio = safe_float(metrics.get("transparent_ratio"))
    edge_density = safe_float(metrics.get("edge_density"))
    gray_entropy = safe_float(metrics.get("gray_entropy"))
    top_color_ratio = safe_float(metrics.get("top_color_ratio"))
    quantized_color_count = safe_int(metrics.get("quantized_color_count"))

    if "filename_palette_marker" in issue_types:
        issue_types.append("palette_or_color_chart_texture")
    elif bright_ratio >= args.palette_bright_ratio and top_color_ratio >= args.palette_top_color_ratio and edge_density >= args.palette_edge_density:
        issue_types.append("visual_palette_or_chart_texture")

    if dark_ratio >= args.fragment_dark_ratio and edge_density >= args.fragment_edge_density:
        issue_types.append("fragmented_uv_dark_seams")
    if transparent_ratio >= args.fragment_transparent_ratio and edge_density >= args.fragment_edge_density:
        issue_types.append("fragmented_uv_transparent_gaps")
    if (
        edge_density >= args.fragment_high_edge_density
        and top_color_ratio <= args.fragment_max_top_color_ratio
        and gray_entropy >= args.fragment_high_entropy
    ):
        issue_types.append("fragmented_uv_high_edges")
    if (
        "filename_generic_image_0" in issue_types
        and edge_density >= args.fragment_generic_edge_density
        and top_color_ratio <= args.fragment_generic_top_color_ratio
        and gray_entropy >= args.fragment_generic_entropy
    ):
        issue_types.append("fragmented_generic_uv_atlas")
    if (
        "filename_temp_or_ai_marker" in issue_types
        and edge_density >= args.fragment_generic_edge_density
        and gray_entropy >= args.fragment_generic_entropy
        and top_color_ratio <= args.fragment_temp_top_color_ratio
        and quantized_color_count >= 24
    ):
        issue_types.append("temp_named_fragmented_texture")

    issue_types = sorted(set(issue_types))
    if any(issue in issue_types for issue in ("palette_or_color_chart_texture", "unreadable_texture")):
        return "texture_problem", issue_types
    if any(issue.startswith("fragmented_") or issue == "temp_named_fragmented_texture" for issue in issue_types):
        return "texture_ai_suspect", issue_types
    if any(issue in issue_types for issue in ("filename_palette_marker", "filename_temp_or_ai_marker")):
        return "texture_review", issue_types
    return "ok", []


def audit_asset(args_tuple: Tuple[Dict[str, str], argparse.Namespace]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    row, args = args_tuple
    path = row.get("path", "")
    relative_path = row.get("relative_path", path)
    folder = relative_path.split("/")[0] if relative_path else "root"
    all_texture_paths = row_texture_paths(row, args.fallback_to_texture_dir)
    texture_paths = filter_texture_paths(all_texture_paths, args)
    image_rows: List[Dict[str, Any]] = []
    finding_rows: List[Dict[str, Any]] = []
    severities: List[str] = []
    max_edge_density = 0.0
    max_dark_ratio = 0.0
    max_bright_ratio = 0.0
    min_top_color_ratio: Optional[float] = None

    for image_path in texture_paths:
        metrics = inspect_texture_image(image_path, args.thumb_size, args.edge_threshold)
        severity, issue_types = classify_texture(metrics, args)
        max_edge_density = max(max_edge_density, safe_float(metrics.get("edge_density")))
        max_dark_ratio = max(max_dark_ratio, safe_float(metrics.get("dark_ratio")))
        max_bright_ratio = max(max_bright_ratio, safe_float(metrics.get("bright_ratio")))
        top_color_ratio = safe_float(metrics.get("top_color_ratio"))
        min_top_color_ratio = top_color_ratio if min_top_color_ratio is None else min(min_top_color_ratio, top_color_ratio)

        if severity == "ok":
            continue
        severities.append(severity)
        image_row = {
            "severity": severity,
            "issue_types": json.dumps(issue_types, ensure_ascii=False),
            "image_path": image_path,
            "file_name": Path(image_path).name,
            "texture_map_kind": metrics.get("texture_map_kind", ""),
            "path": path,
            "relative_path": relative_path,
            "folder": folder,
            "width": metrics.get("width", ""),
            "height": metrics.get("height", ""),
            "aspect_ratio": metrics.get("aspect_ratio", ""),
            "dark_ratio": metrics.get("dark_ratio", ""),
            "bright_ratio": metrics.get("bright_ratio", ""),
            "transparent_ratio": metrics.get("transparent_ratio", ""),
            "edge_density": metrics.get("edge_density", ""),
            "edge_mean": metrics.get("edge_mean", ""),
            "gray_entropy": metrics.get("gray_entropy", ""),
            "top_color_ratio": metrics.get("top_color_ratio", ""),
            "quantized_color_count": metrics.get("quantized_color_count", ""),
        }
        image_rows.append(image_row)
        for issue_type in issue_types:
            finding_rows.append(
                {
                    "severity": severity,
                    "issue": issue_type,
                    "path": path,
                    "relative_path": relative_path,
                    "folder": folder,
                    "image_path": image_path,
                    "details": (
                        f"dark={metrics.get('dark_ratio', '')}, bright={metrics.get('bright_ratio', '')}, "
                        f"edge={metrics.get('edge_density', '')}, entropy={metrics.get('gray_entropy', '')}, "
                        f"top_color={metrics.get('top_color_ratio', '')}"
                    ),
                }
            )

    if not severities:
        return None, image_rows, finding_rows

    if "texture_problem" in severities:
        asset_severity = "texture_problem"
    elif "texture_ai_suspect" in severities:
        asset_severity = "texture_ai_suspect"
    else:
        asset_severity = "texture_review"
    issue_types = sorted(set(issue for image_row in image_rows for issue in parse_jsonish(image_row.get("issue_types", ""), [])))
    asset_row = {
        "severity": asset_severity,
        "texture_issue_types": json.dumps(issue_types, ensure_ascii=False),
        "flagged_texture_count": len(image_rows),
        "texture_count_checked": len(texture_paths),
        "texture_count_total": len(all_texture_paths),
        "skipped_non_color_texture_count": max(len(all_texture_paths) - len(texture_paths), 0),
        "max_edge_density": round(max_edge_density, 6),
        "max_dark_ratio": round(max_dark_ratio, 6),
        "max_bright_ratio": round(max_bright_ratio, 6),
        "min_top_color_ratio": round(min_top_color_ratio or 0.0, 6),
        "path": path,
        "relative_path": relative_path,
        "folder": folder,
        "status": row.get("status", ""),
        "lod": row.get("lod", ""),
        "face_count": row.get("face_count", ""),
        "image_count": row.get("image_count", ""),
        "texture_count": row.get("texture_count", ""),
        "extracted_texture_count": row.get("extracted_texture_count", ""),
        "ai_score": row.get("ai_score", ""),
        "ai_risk": row.get("ai_risk", ""),
        "flagged_textures": json.dumps([image_row["image_path"] for image_row in image_rows], ensure_ascii=False),
    }
    return asset_row, image_rows, finding_rows


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def pct(part: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part / total * 100:.2f}%"


def render_summary_md(summary: Dict[str, Any], folder_rows: Sequence[Dict[str, Any]], top_asset_rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Texture AI/Problem Audit",
        "",
        f"- assets checked: {summary['asset_count']}",
        f"- texture map scope: {summary['texture_map_scope']}",
        f"- textures available: {summary['texture_count_available']}",
        f"- textures checked: {summary['texture_count_checked']}",
        f"- textures skipped as non-color channels: {summary['skipped_non_color_texture_count']}",
        f"- flagged assets: {summary['flagged_asset_count']}",
        f"- flagged textures: {summary['flagged_texture_count']}",
        f"- severity counts: {summary['severity_counts']}",
        f"- issue counts: {summary['issue_counts']}",
        f"- elapsed_sec: {summary['elapsed_sec']}",
        f"- PIL available: {summary['pil_available']}",
        "",
        "## Folder Summary",
        "",
        "| folder | problem | AI suspect | review | total flagged |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in folder_rows:
        lines.append(
            f"| {row['folder']} | {row.get('texture_problem', 0)} | {row.get('texture_ai_suspect', 0)} | "
            f"{row.get('texture_review', 0)} | {row.get('total', 0)} |"
        )
    lines.extend(["", "## Top Flagged Assets", ""])
    if not top_asset_rows:
        lines.append("- No texture AI/problem signals found.")
    else:
        for row in top_asset_rows[:160]:
            lines.append(
                f"- [{row['severity']}] `{row['relative_path']}`: {row['texture_issue_types']} "
                f"textures={row['flagged_texture_count']}/{row['texture_count_checked']}"
            )
    lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    start = time.time()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not PIL_AVAILABLE:
        raise SystemExit("Pillow is required for texture image metrics")

    with Path(args.assets_csv).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.kept_paths:
        kept_paths = {line.strip() for line in Path(args.kept_paths).read_text(encoding="utf-8").splitlines() if line.strip()}
        rows = [row for row in rows if row.get("path") in kept_paths]
    if args.path_contains:
        needles = [needle.lower() for needle in args.path_contains]
        rows = [
            row
            for row in rows
            if any(needle in row.get("path", "").lower() or needle in row.get("relative_path", "").lower() for needle in needles)
        ]
    if args.max_extracted_textures is not None:
        rows = [row for row in rows if safe_int(row.get("extracted_texture_count")) <= args.max_extracted_textures]
    if args.min_extracted_textures is not None:
        rows = [row for row in rows if safe_int(row.get("extracted_texture_count")) >= args.min_extracted_textures]
    rows.sort(key=lambda row: row.get("relative_path", row.get("path", "")))
    if args.max_assets is not None:
        rows = rows[: args.max_assets]

    texture_count_available = sum(len(row_texture_paths(row, args.fallback_to_texture_dir)) for row in rows)
    texture_count_checked = sum(len(filter_texture_paths(row_texture_paths(row, args.fallback_to_texture_dir), args)) for row in rows)
    worker_args = [(row, args) for row in rows]
    asset_rows: List[Dict[str, Any]] = []
    image_rows: List[Dict[str, Any]] = []
    finding_rows: List[Dict[str, Any]] = []

    if args.workers <= 1:
        for completed, item in enumerate(worker_args, start=1):
            asset_row, asset_image_rows, asset_finding_rows = audit_asset(item)
            if asset_row:
                asset_rows.append(asset_row)
            image_rows.extend(asset_image_rows)
            finding_rows.extend(asset_finding_rows)
            if args.progress_every and completed % args.progress_every == 0:
                print(f"progress: {completed}/{len(worker_args)} assets, flagged={len(asset_rows)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(audit_asset, item) for item in worker_args]
            for completed, future in enumerate(as_completed(futures), start=1):
                asset_row, asset_image_rows, asset_finding_rows = future.result()
                if asset_row:
                    asset_rows.append(asset_row)
                image_rows.extend(asset_image_rows)
                finding_rows.extend(asset_finding_rows)
                if args.progress_every and completed % args.progress_every == 0:
                    print(f"progress: {completed}/{len(worker_args)} assets, flagged={len(asset_rows)}", flush=True)

    severity_order = {"texture_problem": 0, "texture_ai_suspect": 1, "texture_review": 2}
    asset_rows.sort(key=lambda row: (severity_order.get(row.get("severity"), 9), row.get("folder", ""), row.get("relative_path", "")))
    image_rows.sort(key=lambda row: (severity_order.get(row.get("severity"), 9), row.get("relative_path", ""), row.get("image_path", "")))
    finding_rows.sort(key=lambda row: (severity_order.get(row.get("severity"), 9), row.get("issue", ""), row.get("relative_path", "")))

    severity_counts = Counter(str(row.get("severity", "")) for row in asset_rows)
    issue_counts = Counter(str(row.get("issue", "")) for row in finding_rows)
    folder_stats: Dict[str, Counter[str]] = defaultdict(Counter)
    for row in asset_rows:
        folder = str(row.get("folder", ""))
        folder_stats[folder][str(row.get("severity", ""))] += 1
        folder_stats[folder]["total"] += 1
    folder_rows = []
    for folder in sorted(folder_stats):
        item = {"folder": folder}
        item.update(folder_stats[folder])
        folder_rows.append(item)

    summary = {
        "source_assets_csv": args.assets_csv,
        "kept_paths": args.kept_paths,
        "asset_count": len(rows),
        "texture_map_scope": args.texture_map_scope,
        "texture_count_available": texture_count_available,
        "texture_count_checked": texture_count_checked,
        "skipped_non_color_texture_count": max(texture_count_available - texture_count_checked, 0),
        "flagged_asset_count": len(asset_rows),
        "flagged_texture_count": len(image_rows),
        "severity_counts": dict(severity_counts.most_common()),
        "issue_counts": dict(issue_counts.most_common()),
        "folder_counts": folder_rows,
        "thresholds": {
            "fragment_dark_ratio": args.fragment_dark_ratio,
            "fragment_edge_density": args.fragment_edge_density,
            "fragment_high_edge_density": args.fragment_high_edge_density,
            "fragment_high_entropy": args.fragment_high_entropy,
            "fragment_generic_edge_density": args.fragment_generic_edge_density,
            "palette_bright_ratio": args.palette_bright_ratio,
            "palette_top_color_ratio": args.palette_top_color_ratio,
        },
        "elapsed_sec": round(time.time() - start, 3),
        "pil_available": PIL_AVAILABLE,
    }

    write_csv(out_dir / "texture_ai_assets.csv", asset_rows, ASSET_FIELDS)
    write_csv(out_dir / "texture_ai_images.csv", image_rows, IMAGE_FIELDS)
    write_csv(out_dir / "texture_ai_findings.csv", finding_rows, FINDING_FIELDS)
    write_csv(out_dir / "texture_ai_folder_summary.csv", folder_rows, ["folder", "texture_problem", "texture_ai_suspect", "texture_review", "total"])
    with (out_dir / "texture_problem_paths.txt").open("w", encoding="utf-8") as handle:
        for row in asset_rows:
            if row.get("severity") == "texture_problem":
                handle.write(str(row.get("path", "")) + "\n")
    with (out_dir / "texture_ai_suspect_paths.txt").open("w", encoding="utf-8") as handle:
        for row in asset_rows:
            if row.get("severity") == "texture_ai_suspect":
                handle.write(str(row.get("path", "")) + "\n")
    with (out_dir / "texture_review_paths.txt").open("w", encoding="utf-8") as handle:
        for row in asset_rows:
            if row.get("severity") == "texture_review":
                handle.write(str(row.get("path", "")) + "\n")
    with (out_dir / "texture_ai_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    with (out_dir / "texture_ai_summary.md").open("w", encoding="utf-8") as handle:
        handle.write(render_summary_md(summary, folder_rows, asset_rows))

    print("===== texture ai audit =====")
    print(f"assets: {len(rows)}")
    print(f"texture_map_scope: {args.texture_map_scope}")
    print(f"textures_available: {texture_count_available}")
    print(f"textures_checked: {texture_count_checked}")
    print(f"textures_skipped_non_color: {max(texture_count_available - texture_count_checked, 0)}")
    print(f"flagged_assets: {len(asset_rows)}")
    print(f"flagged_textures: {len(image_rows)}")
    print(f"severity_counts: {dict(severity_counts.most_common())}")
    print(f"issue_counts: {dict(issue_counts.most_common())}")
    print(f"report_dir: {out_dir}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect texture-side AI/problem signals from extracted texture images")
    parser.add_argument("--assets-csv", required=True, help="assets.csv from glb_quality_audit.py")
    parser.add_argument("--kept-paths", help="Optional deduplicated kept model paths")
    parser.add_argument("--out-dir", required=True, help="Output report directory")
    parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8), help="Parallel worker count")
    parser.add_argument("--max-assets", type=int, help="Optional asset cap for smoke tests")
    parser.add_argument("--path-contains", action="append", help="Only audit rows whose path or relative_path contains this text. Can be repeated")
    parser.add_argument("--max-extracted-textures", type=int, help="Only audit assets with extracted_texture_count <= this value")
    parser.add_argument("--min-extracted-textures", type=int, help="Only audit assets with extracted_texture_count >= this value")
    parser.add_argument("--texture-map-scope", choices=["base-color", "all"], default="base-color", help="Analyze base color candidates only by default; use all to include metallic/roughness/normal channel maps")
    parser.add_argument("--progress-every", type=int, default=1000, help="Print progress every N completed assets; use 0 to disable")
    parser.add_argument("--fallback-to-texture-dir", action=argparse.BooleanOptionalAction, default=False, help="Use all images in texture_extract_dir when extracted_textures is empty")
    parser.add_argument("--thumb-size", type=int, default=512, help="Thumbnail size used for image metrics")
    parser.add_argument("--edge-threshold", type=int, default=28, help="FIND_EDGES threshold used for edge density")
    parser.add_argument("--fragment-dark-ratio", type=float, default=0.25, help="Dark seam ratio threshold for fragmented UV atlases")
    parser.add_argument("--fragment-transparent-ratio", type=float, default=0.20, help="Transparent gap ratio threshold for fragmented UV atlases")
    parser.add_argument("--fragment-edge-density", type=float, default=0.12, help="Edge density paired with dark/transparent fragmented checks")
    parser.add_argument("--fragment-high-edge-density", type=float, default=0.30, help="High edge density threshold for fragmented texture atlases")
    parser.add_argument("--fragment-high-entropy", type=float, default=6.6, help="Entropy floor for high-edge fine fragmented texture atlases")
    parser.add_argument("--fragment-max-top-color-ratio", type=float, default=0.08, help="Top color ratio cap for high-edge fragmented atlases")
    parser.add_argument("--fragment-generic-edge-density", type=float, default=0.12, help="Edge threshold for generic Image_0 atlas checks")
    parser.add_argument("--fragment-generic-top-color-ratio", type=float, default=0.09, help="Top color cap for generic Image_0 atlas checks")
    parser.add_argument("--fragment-generic-entropy", type=float, default=6.3, help="Entropy floor for generic Image_0 atlas checks")
    parser.add_argument("--fragment-temp-top-color-ratio", type=float, default=0.12, help="Top color cap for temp/AI-named fragmented textures")
    parser.add_argument("--palette-bright-ratio", type=float, default=0.25, help="Bright background ratio for visual palette/chart detection")
    parser.add_argument("--palette-top-color-ratio", type=float, default=0.10, help="Dominant color ratio for visual palette/chart detection")
    parser.add_argument("--palette-edge-density", type=float, default=0.10, help="Edge density for visual palette/chart detection")
    args = parser.parse_args(argv)
    if args.workers <= 0:
        parser.error("--workers must be positive")
    if args.thumb_size <= 0:
        parser.error("--thumb-size must be positive")
    if args.max_assets is not None and args.max_assets < 0:
        parser.error("--max-assets must be >= 0")
    if args.max_extracted_textures is not None and args.max_extracted_textures < 0:
        parser.error("--max-extracted-textures must be >= 0")
    if args.min_extracted_textures is not None and args.min_extracted_textures < 0:
        parser.error("--min-extracted-textures must be >= 0")
    if args.progress_every < 0:
        parser.error("--progress-every must be >= 0")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
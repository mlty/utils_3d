#!/usr/bin/env python3
"""Validate extracted GLB texture folders and summarize AI/static audit signals."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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


ASSET_FIELDS = [
    "path",
    "relative_path",
    "folder",
    "status",
    "lod",
    "file_size_mb",
    "face_count",
    "image_count",
    "texture_count",
    "embedded_image_count",
    "external_image_count",
    "extracted_texture_count",
    "actual_image_file_count",
    "output_readable_count",
    "output_unreadable_count",
    "output_min_width",
    "output_min_height",
    "output_max_width",
    "output_max_height",
    "output_small_texture_count",
    "output_large_texture_count",
    "texture_extract_status",
    "count_matches_report",
    "ai_score",
    "ai_risk",
    "ai_suspect",
    "reject_reasons",
    "review_reasons",
    "validation_issues",
]


ISSUE_FIELDS = [
    "severity",
    "issue",
    "path",
    "relative_path",
    "details",
]


def parse_jsonish(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def as_bool(value: Any) -> bool:
    return str(value).casefold() == "true"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def image_files(directory: str) -> List[Path]:
    if not directory:
        return []
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS)


def verify_image(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(path), "readable": False}
    try:
        info["size_bytes"] = path.stat().st_size
        if PIL_AVAILABLE and Image is not None:
            with Image.open(path) as image:
                info["width"], info["height"] = image.size
                info["mode"] = image.mode
                image.verify()
        info["readable"] = True
    except Exception as exc:
        info["error"] = str(exc)
    return info


def validate_one(args: Tuple[Dict[str, str], int, int, bool]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    row, min_texture_size, max_texture_size, verify_images = args
    path = row.get("path", "")
    relative_path = row.get("relative_path", path)
    folder = relative_path.split("/")[0] if relative_path else "root"
    reported_extracted = safe_int(row.get("extracted_texture_count"))
    reported_image_count = safe_int(row.get("image_count"))
    texture_dir = row.get("texture_extract_dir", "")
    files = image_files(texture_dir)
    issues: List[Dict[str, Any]] = []

    def add_issue(severity: str, issue: str, details: str) -> None:
        issues.append(
            {
                "severity": severity,
                "issue": issue,
                "path": path,
                "relative_path": relative_path,
                "details": details,
            }
        )

    if not os.path.exists(path):
        add_issue("error", "missing_model_file", "model file no longer exists on disk")

    if reported_extracted > 0 and not texture_dir:
        add_issue("error", "missing_texture_extract_dir_field", "extracted textures reported but directory field is empty")
    elif reported_extracted > 0 and not Path(texture_dir).is_dir():
        add_issue("error", "missing_texture_extract_dir", texture_dir)

    if len(files) != reported_extracted:
        add_issue(
            "error",
            "extracted_texture_count_mismatch",
            f"reported={reported_extracted}, actual={len(files)}, dir={texture_dir}",
        )

    if reported_image_count == 0:
        add_issue("warn", "asset_has_no_gltf_images", "image_count=0")
    elif reported_extracted < reported_image_count:
        add_issue(
            "warn",
            "fewer_extracted_than_gltf_images",
            f"image_count={reported_image_count}, extracted={reported_extracted}",
        )

    readable_count = 0
    unreadable: List[str] = []
    widths: List[int] = []
    heights: List[int] = []
    small_count = 0
    large_count = 0
    if verify_images:
        for image_path in files:
            info = verify_image(image_path)
            if info.get("readable"):
                readable_count += 1
                width = info.get("width")
                height = info.get("height")
                if isinstance(width, int) and isinstance(height, int):
                    widths.append(width)
                    heights.append(height)
                    if min(width, height) < min_texture_size:
                        small_count += 1
                    if max(width, height) > max_texture_size:
                        large_count += 1
            else:
                unreadable.append(f"{image_path.name}: {info.get('error', 'unreadable')}")
    else:
        readable_count = len(files)

    if unreadable:
        add_issue("error", "unreadable_extracted_image", "; ".join(unreadable[:8]))
    if small_count:
        add_issue("warn", "small_extracted_textures", f"count={small_count}, min_size={min_texture_size}")
    if large_count:
        add_issue("warn", "large_extracted_textures", f"count={large_count}, max_size={max_texture_size}")

    ai_score = safe_int(row.get("ai_score"))
    ai_risk = row.get("ai_risk") or "no_evidence"
    ai_suspect = as_bool(row.get("ai_suspect"))
    if ai_score > 0 or ai_suspect:
        add_issue("review", "ai_candidate", f"score={ai_score}, risk={ai_risk}")

    reject_reasons = parse_jsonish(row.get("reject_reasons", ""), [])
    review_reasons = parse_jsonish(row.get("review_reasons", ""), [])
    if reject_reasons:
        add_issue("error", "audit_rejected_asset", ",".join(str(item) for item in reject_reasons))
    if review_reasons:
        add_issue("review", "audit_review_asset", ",".join(str(item) for item in review_reasons[:8]))

    asset_result = {
        "path": path,
        "relative_path": relative_path,
        "folder": folder,
        "status": row.get("status", ""),
        "lod": row.get("lod", ""),
        "file_size_mb": row.get("file_size_mb", ""),
        "face_count": row.get("face_count", ""),
        "image_count": reported_image_count,
        "texture_count": safe_int(row.get("texture_count")),
        "embedded_image_count": safe_int(row.get("embedded_image_count")),
        "external_image_count": safe_int(row.get("external_image_count")),
        "extracted_texture_count": reported_extracted,
        "actual_image_file_count": len(files),
        "output_readable_count": readable_count,
        "output_unreadable_count": len(unreadable),
        "output_min_width": min(widths) if widths else "",
        "output_min_height": min(heights) if heights else "",
        "output_max_width": max(widths) if widths else "",
        "output_max_height": max(heights) if heights else "",
        "output_small_texture_count": small_count,
        "output_large_texture_count": large_count,
        "texture_extract_status": row.get("texture_extract_status", ""),
        "count_matches_report": len(files) == reported_extracted,
        "ai_score": ai_score,
        "ai_risk": ai_risk,
        "ai_suspect": ai_suspect,
        "reject_reasons": json.dumps(reject_reasons, ensure_ascii=False, sort_keys=True),
        "review_reasons": json.dumps(review_reasons, ensure_ascii=False, sort_keys=True),
        "validation_issues": json.dumps([issue["issue"] for issue in issues], ensure_ascii=False),
    }
    return asset_result, issues


def pct(part: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part / total * 100:.2f}%"


def render_summary_md(summary: Dict[str, Any], folder_rows: Sequence[Dict[str, Any]], top_issue_rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Deep Validation Summary",
        "",
        f"- assets: {summary['asset_count']}",
        f"- actual extracted image files: {summary['actual_image_file_count']}",
        f"- reported extracted texture count: {summary['reported_extracted_texture_count']}",
        f"- output count mismatches: {summary['count_mismatch_assets']}",
        f"- unreadable extracted images: {summary['unreadable_output_image_count']}",
        f"- no-image assets: {summary['no_image_assets']}",
        f"- AI candidates: {summary['ai_candidate_count']}",
        f"- AI risk counts: {summary['ai_risk_counts']}",
        f"- audit status counts: {summary['status_counts']}",
        f"- validation issue counts: {summary['issue_counts']}",
        f"- elapsed_sec: {summary['elapsed_sec']}",
        f"- PIL available: {summary['pil_available']}",
        "",
        "## Folder Summary",
        "",
        "| folder | assets | images | unreadable | mismatches | AI candidates | rejected | review |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in folder_rows:
        lines.append(
            f"| {row['folder']} | {row.get('asset_count', 0)} | {row.get('actual_image_file_count', 0)} | "
            f"{row.get('unreadable_output_image_count', 0)} | {row.get('count_mismatch_assets', 0)} | "
            f"{row.get('ai_candidate_count', 0)} ({pct(int(row.get('ai_candidate_count', 0)), int(row.get('asset_count', 0)))}) | "
            f"{row.get('rejected_count', 0)} | {row.get('review_count', 0)} |"
        )
    lines.extend(["", "## Top Issues", ""])
    if not top_issue_rows:
        lines.append("- No validation issues found.")
    else:
        for row in top_issue_rows[:200]:
            lines.append(
                f"- [{row['severity']}] {row['issue']}: `{row['relative_path']}` - {row['details']}"
            )
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    start = time.time()
    assets_csv = Path(args.assets_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with assets_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    worker_args = [(row, args.min_texture_size, args.max_texture_size, not args.no_image_verify) for row in rows]
    asset_rows: List[Dict[str, Any]] = []
    issue_rows: List[Dict[str, Any]] = []

    if args.workers <= 1:
        for item in worker_args:
            asset_result, issues = validate_one(item)
            asset_rows.append(asset_result)
            issue_rows.extend(issues)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(validate_one, item) for item in worker_args]
            for future in as_completed(futures):
                asset_result, issues = future.result()
                asset_rows.append(asset_result)
                issue_rows.extend(issues)

    asset_rows.sort(key=lambda item: str(item.get("relative_path", "")))
    issue_rows.sort(key=lambda item: (str(item.get("severity", "")), str(item.get("issue", "")), str(item.get("relative_path", ""))))

    folder_stats: Dict[str, Counter[str]] = defaultdict(Counter)
    for row in asset_rows:
        folder = str(row["folder"])
        stats = folder_stats[folder]
        stats["asset_count"] += 1
        stats["actual_image_file_count"] += safe_int(row.get("actual_image_file_count"))
        stats["unreadable_output_image_count"] += safe_int(row.get("output_unreadable_count"))
        if not row.get("count_matches_report"):
            stats["count_mismatch_assets"] += 1
        if safe_int(row.get("ai_score")) > 0 or row.get("ai_suspect") is True:
            stats["ai_candidate_count"] += 1
        if row.get("status") == "rejected":
            stats["rejected_count"] += 1
        if row.get("status") == "review":
            stats["review_count"] += 1

    folder_rows = []
    for folder in sorted(folder_stats):
        row = {"folder": folder}
        row.update(folder_stats[folder])
        folder_rows.append(row)

    status_counts = Counter(str(row.get("status", "unknown")) for row in asset_rows)
    ai_risk_counts = Counter(str(row.get("ai_risk", "no_evidence")) for row in asset_rows)
    issue_counts = Counter(str(row.get("issue", "")) for row in issue_rows)
    summary = {
        "asset_count": len(asset_rows),
        "actual_image_file_count": sum(safe_int(row.get("actual_image_file_count")) for row in asset_rows),
        "reported_extracted_texture_count": sum(safe_int(row.get("extracted_texture_count")) for row in asset_rows),
        "count_mismatch_assets": sum(1 for row in asset_rows if not row.get("count_matches_report")),
        "unreadable_output_image_count": sum(safe_int(row.get("output_unreadable_count")) for row in asset_rows),
        "no_image_assets": sum(1 for row in asset_rows if safe_int(row.get("image_count")) == 0),
        "ai_candidate_count": sum(1 for row in asset_rows if safe_int(row.get("ai_score")) > 0 or row.get("ai_suspect") is True),
        "status_counts": dict(status_counts),
        "ai_risk_counts": dict(ai_risk_counts),
        "issue_counts": dict(issue_counts.most_common()),
        "elapsed_sec": round(time.time() - start, 3),
        "pil_available": PIL_AVAILABLE,
        "source_assets_csv": str(assets_csv),
        "verify_images": not args.no_image_verify,
        "min_texture_size": args.min_texture_size,
        "max_texture_size": args.max_texture_size,
    }

    write_csv(out_dir / "deep_validation_assets.csv", asset_rows, ASSET_FIELDS)
    write_csv(out_dir / "deep_validation_issues.csv", issue_rows, ISSUE_FIELDS)
    write_csv(
        out_dir / "deep_validation_folder_summary.csv",
        folder_rows,
        [
            "folder",
            "asset_count",
            "actual_image_file_count",
            "unreadable_output_image_count",
            "count_mismatch_assets",
            "ai_candidate_count",
            "rejected_count",
            "review_count",
        ],
    )
    with (out_dir / "deep_validation_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    with (out_dir / "deep_validation_summary.md").open("w", encoding="utf-8") as handle:
        handle.write(render_summary_md(summary, folder_rows, issue_rows))

    print("===== deep validation =====")
    print(f"assets: {summary['asset_count']}")
    print(f"actual_image_file_count: {summary['actual_image_file_count']}")
    print(f"count_mismatch_assets: {summary['count_mismatch_assets']}")
    print(f"unreadable_output_image_count: {summary['unreadable_output_image_count']}")
    print(f"ai_candidate_count: {summary['ai_candidate_count']}")
    print(f"issue_counts: {summary['issue_counts']}")
    print(f"report_dir: {out_dir}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate extracted texture folders from glb_quality_audit assets.csv")
    parser.add_argument("--assets-csv", required=True, help="Path to assets.csv produced by glb_quality_audit.py")
    parser.add_argument("--out-dir", required=True, help="Output directory for validation reports")
    parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8), help="Parallel worker count")
    parser.add_argument("--min-texture-size", type=int, default=64, help="Warn when any output image side is below this")
    parser.add_argument("--max-texture-size", type=int, default=8192, help="Warn when any output image side is above this")
    parser.add_argument("--no-image-verify", action="store_true", help="Skip PIL image open/verify for extracted images")
    args = parser.parse_args(argv)
    if args.workers <= 0:
        parser.error("--workers must be positive")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Summarize GLB triangle-count buckets for a jiaguyi-style data root."""

from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any


GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
NATIVE_MODEL_EXTENSIONS = {".glb", ".gltf"}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_gltf(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if path.suffix.lower() == ".gltf":
        return json.loads(data.decode("utf-8"))

    if len(data) < 20:
        raise ValueError("GLB too small")

    magic, _, _ = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("not a GLB file")

    offset = 12
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == JSON_CHUNK:
            return json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))

    raise ValueError("GLB JSON chunk missing")


def count_faces_for_primitive(primitive: dict[str, Any], accessors: list[Any]) -> int:
    mode = int(primitive.get("mode", 4))
    attributes = as_dict(primitive.get("attributes"))
    vertex_count = 0
    index_count = 0

    position_index = attributes.get("POSITION")
    if isinstance(position_index, int) and 0 <= position_index < len(accessors):
        vertex_count = int(as_dict(accessors[position_index]).get("count", 0) or 0)

    indices_index = primitive.get("indices")
    if isinstance(indices_index, int) and 0 <= indices_index < len(accessors):
        index_count = int(as_dict(accessors[indices_index]).get("count", 0) or 0)

    element_count = index_count or vertex_count
    if mode == 4:
        return element_count // 3
    if mode in {5, 6}:
        return max(0, element_count - 2)
    return 0


def count_model_faces(path: Path) -> tuple[int, int, int]:
    gltf = load_gltf(path)
    accessors = gltf.get("accessors") or []
    face_count = 0
    mesh_count = 0
    primitive_count = 0

    for mesh in gltf.get("meshes") or []:
        mesh_count += 1
        for primitive in as_dict(mesh).get("primitives") or []:
            primitive_count += 1
            face_count += count_faces_for_primitive(as_dict(primitive), accessors)

    return face_count, mesh_count, primitive_count


def classify_bucket(face_count: int) -> str:
    if face_count < 1000:
        return "under_1k"
    if face_count < 50000:
        return "low_1k_50k"
    if face_count < 150000:
        return "mid_50k_150k"
    if face_count <= 300000:
        return "high_150k_300k"
    return "over_300k"


def percentage(value: int, total: int) -> str:
    if total == 0:
        return "0.00%"
    return f"{value / total * 100:.2f}%"


def iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def update_face_stats(stats: dict[str, int], face_count: int, bucket: str) -> None:
    stats["parsed"] += 1
    stats[bucket] += 1
    stats["faces_total"] += face_count
    stats["faces_min"] = face_count if "faces_min" not in stats else min(stats["faces_min"], face_count)
    stats["faces_max"] = max(stats.get("faces_max", 0), face_count)


def build_summary(root: Path, extra_details: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    details: list[dict[str, Any]] = []

    for path in iter_files(root):
        folder = path.relative_to(root).parts[0]
        extension = path.suffix.lower() or "[no_ext]"
        stats[folder]["all_files"] += 1
        stats[folder][f"ext_{extension}"] += 1

        if extension not in NATIVE_MODEL_EXTENSIONS:
            continue

        stats[folder]["model_files"] += 1
        try:
            face_count, mesh_count, primitive_count = count_model_faces(path)
            bucket = classify_bucket(face_count)
            update_face_stats(stats[folder], face_count, bucket)
            details.append(
                {
                    "folder": folder,
                    "path": str(path),
                    "faces": face_count,
                    "bucket": bucket,
                    "mesh_count": mesh_count,
                    "primitive_count": primitive_count,
                    "error": "",
                }
            )
        except Exception as exc:
            stats[folder]["parse_failed"] += 1
            details.append(
                {
                    "folder": folder,
                    "path": str(path),
                    "faces": "",
                    "bucket": "parse_failed",
                    "mesh_count": "",
                    "primitive_count": "",
                    "error": repr(exc),
                }
            )

    for details_path in extra_details:
        with details_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                folder = row.get("folder") or Path(row["path"]).relative_to(root).parts[0]
                bucket = row.get("bucket", "parse_failed")
                if bucket == "parse_failed":
                    stats[folder]["parse_failed"] += 1
                else:
                    update_face_stats(stats[folder], int(row["faces"]), bucket)
                details.append(row)

    rows: list[dict[str, Any]] = []
    for folder in sorted(stats):
        item = stats[folder]
        parsed = item.get("parsed", 0)
        rows.append(
            {
                "folder": folder,
                "all_files": item.get("all_files", 0),
                "glb": item.get("ext_.glb", 0),
                "gltf": item.get("ext_.gltf", 0),
                "fbx": item.get("ext_.fbx", 0),
                "json": item.get("ext_.json", 0),
                "parsed": parsed,
                "parse_failed": item.get("parse_failed", 0),
                "under_1k": item.get("under_1k", 0),
                "low_1k_50k": item.get("low_1k_50k", 0),
                "mid_50k_150k": item.get("mid_50k_150k", 0),
                "high_150k_300k": item.get("high_150k_300k", 0),
                "over_300k": item.get("over_300k", 0),
                "faces_min": item.get("faces_min", 0),
                "faces_max": item.get("faces_max", 0),
                "avg_faces": round(item.get("faces_total", 0) / parsed) if parsed else 0,
            }
        )

    return rows, details


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, Any]]) -> str:
    totals = defaultdict(int)
    face_mins = [row["faces_min"] for row in rows if row["parsed"]]
    face_maxes = [row["faces_max"] for row in rows if row["parsed"]]
    total_faces = sum(row["avg_faces"] * row["parsed"] for row in rows)

    lines = [
        "# jiaguyi poly statistics",
        "",
        "Thresholds: under_1k: <1,000; low: 1,000-49,999; mid: 50,000-149,999; high: 150,000-300,000; over_300k: >300,000 triangles.",
        "",
        "| folder | all files | GLB | FBX | JSON | parsed models | failed | <1k | low | mid | high | >300k | min faces | max faces | avg faces |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        for key, value in row.items():
            if isinstance(value, int):
                totals[key] += value
        lines.append(
            f"| {row['folder']} | {row['all_files']} | {row['glb']} | {row['fbx']} | {row['json']} | {row['parsed']} | {row['parse_failed']} | {row['under_1k']} | {row['low_1k_50k']} | {row['mid_50k_150k']} | {row['high_150k_300k']} | {row['over_300k']} | {row['faces_min']} | {row['faces_max']} | {row['avg_faces']} |"
        )

    total_parsed = totals["parsed"]
    avg_faces = round(total_faces / total_parsed) if total_parsed else 0
    lines.append(
        f"| TOTAL | {totals['all_files']} | {totals['glb']} | {totals['fbx']} | {totals['json']} | {total_parsed} | {totals['parse_failed']} | {totals['under_1k']} | {totals['low_1k_50k']} | {totals['mid_50k_150k']} | {totals['high_150k_300k']} | {totals['over_300k']} | {min(face_mins) if face_mins else 0} | {max(face_maxes) if face_maxes else 0} | {avg_faces} |"
    )

    lines.extend(
        [
            "",
            "## Percent of parsed models",
            "",
            "| folder | low | mid | high | in target range | outside range |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        parsed = row["parsed"]
        target = row["low_1k_50k"] + row["mid_50k_150k"] + row["high_150k_300k"]
        outside = row["under_1k"] + row["over_300k"]
        lines.append(
            f"| {row['folder']} | {percentage(row['low_1k_50k'], parsed)} | {percentage(row['mid_50k_150k'], parsed)} | {percentage(row['high_150k_300k'], parsed)} | {percentage(target, parsed)} | {percentage(outside, parsed)} |"
        )

    target = totals["low_1k_50k"] + totals["mid_50k_150k"] + totals["high_150k_300k"]
    outside = totals["under_1k"] + totals["over_300k"]
    lines.append(
        f"| TOTAL | {percentage(totals['low_1k_50k'], total_parsed)} | {percentage(totals['mid_50k_150k'], total_parsed)} | {percentage(totals['high_150k_300k'], total_parsed)} | {percentage(target, total_parsed)} | {percentage(outside, total_parsed)} |"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--extra-details", type=Path, action="append", default=[])
    args = parser.parse_args()

    rows, details = build_summary(args.root, args.extra_details)
    write_csv(args.details, details)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    summary = markdown_table(rows)
    args.summary.write_text(summary, encoding="utf-8")
    print(summary)
    print(f"Details CSV: {args.details}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
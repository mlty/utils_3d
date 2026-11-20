#!/usr/bin/env python3
"""Count FBX triangle buckets with Blender for a jiaguyi-style data root."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import bpy


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


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def count_mesh_triangles() -> tuple[int, int, int]:
    face_count = 0
    mesh_count = 0
    primitive_count = 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        mesh_count += 1
        mesh = obj.data
        primitive_count += len(mesh.polygons)
        face_count += sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons)
    return face_count, mesh_count, primitive_count


def parse_args() -> argparse.Namespace:
    argv = []
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--details", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    rows = []
    for path in sorted(args.root.rglob("*.fbx")):
        folder = path.relative_to(args.root).parts[0]
        clear_scene()
        try:
            bpy.ops.import_scene.fbx(filepath=str(path))
            face_count, mesh_count, primitive_count = count_mesh_triangles()
            rows.append(
                {
                    "folder": folder,
                    "path": str(path),
                    "faces": face_count,
                    "bucket": classify_bucket(face_count),
                    "mesh_count": mesh_count,
                    "primitive_count": primitive_count,
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
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

    args.details.parent.mkdir(parents=True, exist_ok=True)
    with args.details.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["folder", "path", "faces", "bucket", "mesh_count", "primitive_count", "error"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} FBX rows to {args.details}")


if __name__ == "__main__":
    main()
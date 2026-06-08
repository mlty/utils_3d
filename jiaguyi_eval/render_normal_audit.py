#!/usr/bin/env python3
"""Render GLB normal views and score geometric sharpness/detail.

The script reads assets.csv from glb_quality_audit.py, selects low-texture and
already-problematic assets, renders six normal-visualization views with Blender,
then computes simple image statistics that highlight flat, blurry, or weak 3D
geometry signals.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
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

try:
    np = importlib.import_module("numpy")
    NUMPY_AVAILABLE = True
except Exception:
    np = None
    NUMPY_AVAILABLE = False


VIEW_NAMES = ("front", "back", "left", "right", "top", "bottom")

DEFAULT_PROBLEM_ISSUES = {
    "ai_candidate",
    "asset_has_no_gltf_images",
    "audit_rejected_asset",
    "fewer_extracted_than_gltf_images",
    "large_extracted_textures",
    "missing_model_file",
    "missing_texture_extract_dir",
    "missing_texture_extract_dir_field",
    "small_extracted_textures",
    "unreadable_extracted_image",
}

CANDIDATE_FIELDS = [
    "path",
    "relative_path",
    "status",
    "lod",
    "face_count",
    "vertex_count",
    "image_count",
    "texture_count",
    "extracted_texture_count",
    "ai_score",
    "ai_risk",
    "candidate_reasons",
    "validation_issues",
    "reject_reasons",
    "review_reasons",
]

ASSET_FIELDS = [
    "path",
    "relative_path",
    "status",
    "lod",
    "face_count",
    "vertex_count",
    "image_count",
    "texture_count",
    "extracted_texture_count",
    "ai_score",
    "ai_risk",
    "candidate_reasons",
    "render_status",
    "render_dir",
    "render_images",
    "visible_view_count",
    "object_pixel_ratio_mean",
    "object_pixel_ratio_min",
    "normal_gradient_mean",
    "normal_gradient_p95_mean",
    "normal_laplacian_var_mean",
    "normal_entropy_mean",
    "normal_unique_bins_mean",
    "normal_color_range_mean",
    "normal_detail_score",
    "normal_sharpness_score",
    "geometry_signal_score",
    "normal_quality_action",
    "normal_flags",
    "render_error",
]

VIEW_FIELDS = [
    "path",
    "relative_path",
    "view",
    "image_path",
    "readable",
    "width",
    "height",
    "object_pixel_count",
    "object_pixel_ratio",
    "gradient_mean",
    "gradient_p95",
    "laplacian_var",
    "entropy",
    "unique_bins",
    "color_range_mean",
    "error",
]


BLENDER_NORMAL_SCRIPT = r'''
import json
import math
import os
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


VIEW_DIRECTIONS = {
    "front": Vector((0.0, -1.0, 0.0)),
    "back": Vector((0.0, 1.0, 0.0)),
    "left": Vector((-1.0, 0.0, 0.0)),
    "right": Vector((1.0, 0.0, 0.0)),
    "top": Vector((0.0, 0.0, 1.0)),
    "bottom": Vector((0.0, 0.0, -1.0)),
}


def parse_args():
    argv = sys.argv
    if "--" not in argv:
        raise SystemExit("missing -- render args")
    args = argv[argv.index("--") + 1:]
    if len(args) != 2:
        raise SystemExit("usage: blender --background --python normal.py -- jobs.json results.jsonl")
    return args[0], args[1]


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(path):
    suffix = Path(path).suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise ValueError(f"unsupported render extension: {suffix}")


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def compute_bounds(objects):
    min_corner = Vector((math.inf, math.inf, math.inf))
    max_corner = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            min_corner.x = min(min_corner.x, world_corner.x)
            min_corner.y = min(min_corner.y, world_corner.y)
            min_corner.z = min(min_corner.z, world_corner.z)
            max_corner.x = max(max_corner.x, world_corner.x)
            max_corner.y = max(max_corner.y, world_corner.y)
            max_corner.z = max(max_corner.z, world_corner.z)
    return min_corner, max_corner


def look_at(camera, target):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_render_engine(scene, requested_engine):
    candidates = []
    if requested_engine:
        candidates.append(requested_engine)
    candidates.extend(["BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"])
    seen = set()
    for engine in candidates:
        if engine in seen:
            continue
        seen.add(engine)
        try:
            scene.render.engine = engine
            return engine
        except Exception:
            pass
    raise ValueError("no supported Blender render engine found")


def setup_render(size, engine):
    scene = bpy.context.scene
    used_engine = set_render_engine(scene, engine)
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    try:
        scene.eevee.taa_samples = 16
    except Exception:
        pass
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
    except Exception:
        pass
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (0.0, 0.0, 0.0)
    return used_engine


def create_normal_material():
    material = bpy.data.materials.new("Normal_Visualizer")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    links = material.node_tree.links

    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission = nodes.new(type="ShaderNodeEmission")
    geometry = nodes.new(type="ShaderNodeNewGeometry")
    add_node = nodes.new(type="ShaderNodeVectorMath")
    add_node.operation = "ADD"
    add_node.inputs[1].default_value = (1.0, 1.0, 1.0)
    scale_node = nodes.new(type="ShaderNodeVectorMath")
    scale_node.operation = "MULTIPLY"
    scale_node.inputs[1].default_value = (0.5, 0.5, 0.5)

    emission.inputs["Strength"].default_value = 1.0
    links.new(geometry.outputs["Normal"], add_node.inputs[0])
    links.new(add_node.outputs["Vector"], scale_node.inputs[0])
    links.new(scale_node.outputs["Vector"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def assign_normal_material(objects):
    material = create_normal_material()
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        try:
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
        except Exception:
            pass


def render_job(job):
    path = job["path"]
    render_dir = job["render_dir"]
    prefix = job["prefix"]
    size = int(job["size"])
    engine = job.get("engine")
    result = {"path": path, "status": "ok", "images": [], "errors": [], "engine": None}
    try:
        reset_scene()
        import_model(path)
        objects = mesh_objects()
        if not objects:
            raise ValueError("no mesh objects after import")
        assign_normal_material(objects)
        min_corner, max_corner = compute_bounds(objects)
        center = (min_corner + max_corner) / 2.0
        extents = max_corner - min_corner
        max_extent = max(extents.x, extents.y, extents.z, 1e-3)
        distance = max(max_extent * 2.2, 1.0)
        result["engine"] = setup_render(size, engine)

        camera_data = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", camera_data)
        bpy.context.collection.objects.link(camera)
        bpy.context.scene.camera = camera
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = max_extent * 1.35
        camera_data.clip_start = 0.001
        camera_data.clip_end = max(distance * 6.0, 1000.0)

        os.makedirs(render_dir, exist_ok=True)
        for view_name, direction in VIEW_DIRECTIONS.items():
            camera.location = center + direction.normalized() * distance
            look_at(camera, center)
            image_path = os.path.join(render_dir, f"{prefix}_normal_{view_name}.png")
            bpy.context.scene.render.filepath = image_path
            bpy.ops.render.render(write_still=True)
            result["images"].append(image_path)
    except Exception as exc:
        result["status"] = "failed"
        result["errors"].append(str(exc))
        result["traceback"] = traceback.format_exc()
    return result


def main():
    jobs_path, results_path = parse_args()
    with open(jobs_path, "r", encoding="utf-8") as handle:
        jobs = json.load(handle)
    with open(results_path, "w", encoding="utf-8") as writer:
        for job in jobs:
            result = render_job(job)
            writer.write(json.dumps(result, ensure_ascii=False) + "\n")
            writer.flush()


if __name__ == "__main__":
    main()
'''


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


def as_bool(value: Any) -> bool:
    return str(value).casefold() == "true"


def parse_jsonish(value: str, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed


def parse_csv_set(raw: str) -> set:
    return {item.strip() for item in raw.split(",") if item.strip()}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def pct(part: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part / total * 100:.2f}%"


def sanitize_name(value: str, fallback: str = "asset") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", value).strip("._-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:96]


def asset_key(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8", errors="replace")).hexdigest()[:12]


def asset_folder(relative_path: str) -> str:
    if not relative_path:
        return "root"
    return relative_path.split("/")[0] or "root"


def render_dir_for_asset(out_dir: Path, row: Dict[str, str]) -> Path:
    path = row.get("path", "")
    relative_path = row.get("relative_path") or Path(path).name
    folder = sanitize_name(asset_folder(relative_path), "root")
    stem = sanitize_name(Path(path).stem, "asset")
    return out_dir / "normal_renders" / folder / f"{stem}_{asset_key(path)}"


def render_prefix_for_asset(row: Dict[str, str]) -> str:
    stem = sanitize_name(Path(row.get("path", "asset")).stem, "asset")
    return f"{stem}_{asset_key(row.get('path', ''))}"


def expected_render_images(out_dir: Path, row: Dict[str, str]) -> List[str]:
    render_dir = render_dir_for_asset(out_dir, row)
    prefix = render_prefix_for_asset(row)
    return [str(render_dir / f"{prefix}_normal_{view}.png") for view in VIEW_NAMES]


def find_blender_executable(blender_path: Optional[str]) -> Optional[str]:
    candidates = [
        blender_path,
        os.environ.get("BLENDER_PATH"),
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_validation_issue_map(
    issues_csv: Optional[str],
    issue_names: set,
    include_all_issues: bool,
) -> Dict[str, List[str]]:
    if not issues_csv:
        return {}
    issue_path = Path(issues_csv)
    if not issue_path.exists():
        return {}
    issue_map: Dict[str, List[str]] = defaultdict(list)
    with issue_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            issue = row.get("issue", "")
            if include_all_issues or issue in issue_names:
                path = row.get("path", "")
                if path:
                    issue_map[path].append(issue)
    return issue_map


def candidate_reasons_for_row(
    row: Dict[str, str],
    validation_issues: Sequence[str],
    max_texture_count: int,
    problem_statuses: set,
    include_ai: bool,
) -> List[str]:
    reasons: List[str] = []
    extracted_count = safe_int(row.get("extracted_texture_count"))
    if extracted_count <= max_texture_count:
        reasons.append(f"texture_count_le_{max_texture_count}")

    status = row.get("status", "")
    if status in problem_statuses:
        reasons.append(f"status_{status}")

    ai_score = safe_int(row.get("ai_score"))
    if include_ai and (ai_score > 0 or as_bool(row.get("ai_suspect"))):
        reasons.append("ai_candidate")

    for issue in sorted(set(validation_issues)):
        reasons.append(f"validation_{issue}")

    return reasons


def candidate_priority(row: Dict[str, str]) -> Tuple[int, int, int, str]:
    reasons = parse_jsonish(row.get("candidate_reasons", ""), [])
    reason_text = " ".join(str(item) for item in reasons)
    problem_rank = 0 if any(token in reason_text for token in ("status_rejected", "ai_candidate", "validation_")) else 1
    texture_count = safe_int(row.get("extracted_texture_count"), 999999)
    face_count = safe_int(row.get("face_count"), 999999999)
    return (problem_rank, texture_count, face_count, row.get("relative_path", row.get("path", "")))


def select_candidates(
    rows: Sequence[Dict[str, str]],
    validation_issue_map: Dict[str, List[str]],
    max_texture_count: int,
    problem_statuses: set,
    include_ai: bool,
) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    for row in rows:
        reasons = candidate_reasons_for_row(
            row,
            validation_issue_map.get(row.get("path", ""), []),
            max_texture_count,
            problem_statuses,
            include_ai,
        )
        if not reasons:
            continue
        selected = dict(row)
        selected["candidate_reasons"] = json.dumps(sorted(set(reasons)), ensure_ascii=False)
        selected["validation_issues"] = json.dumps(sorted(set(validation_issue_map.get(row.get("path", ""), []))), ensure_ascii=False)
        candidates.append(selected)
    candidates.sort(key=candidate_priority)
    return candidates


def choose_render_rows(candidates: Sequence[Dict[str, str]], args: argparse.Namespace) -> List[Dict[str, str]]:
    rows = list(candidates)
    if args.selection_order == "random":
        rng = random.Random(args.sample_seed)
        rng.shuffle(rows)
    elif args.selection_order == "path":
        rows.sort(key=lambda item: item.get("relative_path", item.get("path", "")))
    else:
        rows.sort(key=candidate_priority)

    if args.max_render_assets > 0:
        rows = rows[: args.max_render_assets]
    return rows


def existing_normal_images(out_dir: Path, row: Dict[str, str]) -> List[str]:
    images = expected_render_images(out_dir, row)
    if all(Path(image_path).exists() for image_path in images):
        return images
    return []


def render_normal_views(rows: Sequence[Dict[str, str]], args: argparse.Namespace, out_dir: Path) -> Dict[str, Dict[str, Any]]:
    result_by_path: Dict[str, Dict[str, Any]] = {}
    jobs: List[Dict[str, Any]] = []
    for row in rows:
        path = row.get("path", "")
        existing_images = [] if args.overwrite else existing_normal_images(out_dir, row)
        if existing_images:
            result_by_path[path] = {"path": path, "status": "existing", "images": existing_images, "errors": []}
            continue
        jobs.append(
            {
                "path": path,
                "render_dir": str(render_dir_for_asset(out_dir, row)),
                "prefix": render_prefix_for_asset(row),
                "size": args.render_size,
                "engine": args.render_engine,
            }
        )

    if not jobs:
        return result_by_path

    blender = find_blender_executable(args.blender_path)
    if not blender:
        for row in rows:
            path = row.get("path", "")
            if path not in result_by_path:
                result_by_path[path] = {"path": path, "status": "skipped_no_blender", "images": [], "errors": ["Blender executable not found"]}
        return result_by_path

    with tempfile.NamedTemporaryFile("w", suffix="_normal_render.py", delete=False, encoding="utf-8") as script_file:
        script_file.write(BLENDER_NORMAL_SCRIPT)
        script_path = script_file.name

    jobs_path = out_dir / "normal_render_jobs.json"
    results_path = out_dir / "normal_render_results.jsonl"
    with jobs_path.open("w", encoding="utf-8") as writer:
        json.dump(jobs, writer, ensure_ascii=False, indent=2)

    command = [blender, "--background", "--factory-startup", "--python", script_path, "--", str(jobs_path), str(results_path)]
    timeout = max(args.render_timeout_sec, args.render_timeout_sec * max(len(jobs), 1))
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or str(exc))[-4000:]
        for row in rows:
            path = row.get("path", "")
            if path not in result_by_path:
                result_by_path[path] = {"path": path, "status": "failed", "images": [], "errors": [error_text]}
        return result_by_path
    except subprocess.TimeoutExpired as exc:
        error_text = f"Blender normal render timed out after {timeout}s: {exc}"
        for row in rows:
            path = row.get("path", "")
            if path not in result_by_path:
                result_by_path[path] = {"path": path, "status": "failed", "images": [], "errors": [error_text]}
        return result_by_path
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    if results_path.exists():
        with results_path.open("r", encoding="utf-8") as reader:
            for line in reader:
                if line.strip():
                    result = json.loads(line)
                    result_by_path[str(result.get("path"))] = result

    for job in jobs:
        path = str(job.get("path"))
        if path not in result_by_path:
            result_by_path[path] = {"path": path, "status": "failed", "images": [], "errors": ["missing Blender render result"]}
    return result_by_path


def shifted_mask(mask: Any, row_shift: int, column_shift: int) -> Any:
    shifted = np.zeros_like(mask)
    source_rows = slice(max(0, -row_shift), mask.shape[0] - max(0, row_shift))
    target_rows = slice(max(0, row_shift), mask.shape[0] - max(0, -row_shift))
    source_columns = slice(max(0, -column_shift), mask.shape[1] - max(0, column_shift))
    target_columns = slice(max(0, column_shift), mask.shape[1] - max(0, -column_shift))
    shifted[target_rows, target_columns] = mask[source_rows, source_columns]
    return shifted


def image_metrics_numpy(image_path: str, alpha_threshold: int, gradient_edge_threshold: float) -> Dict[str, Any]:
    if not PIL_AVAILABLE or Image is None:
        return {"readable": False, "error": "PIL is not available"}
    if not NUMPY_AVAILABLE or np is None:
        return {"readable": False, "error": "numpy is not available"}
    try:
        with Image.open(image_path) as image:
            rgba_image = image.convert("RGBA")
            width, height = rgba_image.size
            array = np.asarray(rgba_image, dtype=np.float32)
    except Exception as exc:
        return {"readable": False, "error": str(exc)}

    alpha = array[:, :, 3]
    mask = alpha > alpha_threshold
    object_pixel_count = int(mask.sum())
    total_pixels = int(mask.size)
    object_pixel_ratio = object_pixel_count / max(total_pixels, 1)
    base = {
        "readable": True,
        "width": width,
        "height": height,
        "object_pixel_count": object_pixel_count,
        "object_pixel_ratio": round(object_pixel_ratio, 6),
    }
    if object_pixel_count <= 0:
        base.update(
            {
                "gradient_mean": 0.0,
                "gradient_p95": 0.0,
                "laplacian_var": 0.0,
                "entropy": 0.0,
                "unique_bins": 0,
                "color_range_mean": 0.0,
                "edge_density": 0.0,
            }
        )
        return base

    rgb = array[:, :, :3]
    gray = rgb.mean(axis=2)

    horizontal_mask = mask[:, 1:] & mask[:, :-1]
    vertical_mask = mask[1:, :] & mask[:-1, :]
    horizontal_diff = np.abs(gray[:, 1:] - gray[:, :-1])[horizontal_mask]
    vertical_diff = np.abs(gray[1:, :] - gray[:-1, :])[vertical_mask]
    if horizontal_diff.size or vertical_diff.size:
        gradient_values = np.concatenate([horizontal_diff, vertical_diff])
        gradient_mean = float(np.mean(gradient_values))
        gradient_p95 = float(np.percentile(gradient_values, 95))
        edge_density = float(np.mean(gradient_values > gradient_edge_threshold))
    else:
        gradient_mean = 0.0
        gradient_p95 = 0.0
        edge_density = 0.0

    center_mask = mask[1:-1, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:] & mask[:-2, 1:-1] & mask[2:, 1:-1]
    if center_mask.any():
        laplacian = (
            -4.0 * gray[1:-1, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
            + gray[:-2, 1:-1]
            + gray[2:, 1:-1]
        )
        laplacian_values = laplacian[center_mask]
        laplacian_var = float(np.var(laplacian_values)) if laplacian_values.size else 0.0
    else:
        laplacian_var = 0.0

    object_rgb = rgb[mask]
    if object_rgb.size:
        color_min = np.percentile(object_rgb, 5, axis=0)
        color_max = np.percentile(object_rgb, 95, axis=0)
        color_range_mean = float(np.mean(color_max - color_min))
        quantized = np.clip((object_rgb / 16.0).astype(np.int16), 0, 15)
        bins = quantized[:, 0] * 256 + quantized[:, 1] * 16 + quantized[:, 2]
        _, counts = np.unique(bins, return_counts=True)
        probabilities = counts.astype(np.float64) / max(counts.sum(), 1)
        entropy = float(-np.sum(probabilities * np.log2(probabilities)))
        unique_bins = int(len(counts))
    else:
        color_range_mean = 0.0
        entropy = 0.0
        unique_bins = 0

    base.update(
        {
            "gradient_mean": round(gradient_mean, 6),
            "gradient_p95": round(gradient_p95, 6),
            "laplacian_var": round(laplacian_var, 6),
            "entropy": round(entropy, 6),
            "unique_bins": unique_bins,
            "color_range_mean": round(color_range_mean, 6),
            "edge_density": round(edge_density, 6),
        }
    )
    return base


def percentile_from_histogram(histogram: Sequence[int], percentile: float) -> float:
    total = sum(histogram)
    if total <= 0:
        return 0.0
    target = total * percentile
    running = 0
    for value, count in enumerate(histogram):
        running += int(count)
        if running >= target:
            return float(value)
    return float(len(histogram) - 1)


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


def image_metrics_pil(image_path: str, alpha_threshold: int, gradient_edge_threshold: float) -> Dict[str, Any]:
    if not PIL_AVAILABLE or Image is None or ImageFilter is None or ImageStat is None:
        return {"readable": False, "error": "PIL is not available"}
    try:
        with Image.open(image_path) as image:
            rgba_image = image.convert("RGBA")
    except Exception as exc:
        return {"readable": False, "error": str(exc)}

    width, height = rgba_image.size
    alpha = rgba_image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > alpha_threshold else 0)
    mask_histogram = mask.histogram()
    object_pixel_count = sum(mask_histogram[1:])
    total_pixels = width * height
    object_pixel_ratio = object_pixel_count / max(total_pixels, 1)
    if object_pixel_count <= 0:
        return {
            "readable": True,
            "width": width,
            "height": height,
            "object_pixel_count": object_pixel_count,
            "object_pixel_ratio": round(object_pixel_ratio, 6),
            "gradient_mean": 0.0,
            "gradient_p95": 0.0,
            "laplacian_var": 0.0,
            "entropy": 0.0,
            "unique_bins": 0,
            "color_range_mean": 0.0,
            "edge_density": 0.0,
        }

    gray = rgba_image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_stats = ImageStat.Stat(edges, mask=mask)
    edge_histogram = edges.histogram(mask=mask)
    gray_histogram = gray.histogram(mask=mask)
    gradient_mean = float(edge_stats.mean[0]) if edge_stats.mean else 0.0
    gradient_p95 = percentile_from_histogram(edge_histogram, 0.95)
    laplacian_var = float(edge_stats.var[0]) if edge_stats.var else 0.0
    entropy = entropy_from_histogram(gray_histogram)
    unique_bins = sum(1 for count in gray_histogram if count)
    color_range_mean = percentile_from_histogram(gray_histogram, 0.95) - percentile_from_histogram(gray_histogram, 0.05)
    edge_count = sum(count for value, count in enumerate(edge_histogram) if value > gradient_edge_threshold)
    edge_density = edge_count / max(sum(edge_histogram), 1)

    return {
        "readable": True,
        "width": width,
        "height": height,
        "object_pixel_count": object_pixel_count,
        "object_pixel_ratio": round(object_pixel_ratio, 6),
        "gradient_mean": round(gradient_mean, 6),
        "gradient_p95": round(gradient_p95, 6),
        "laplacian_var": round(laplacian_var, 6),
        "entropy": round(entropy, 6),
        "unique_bins": unique_bins,
        "color_range_mean": round(color_range_mean, 6),
        "edge_density": round(edge_density, 6),
    }


def image_metrics(image_path: str, alpha_threshold: int, gradient_edge_threshold: float) -> Dict[str, Any]:
    if NUMPY_AVAILABLE and np is not None:
        return image_metrics_numpy(image_path, alpha_threshold, gradient_edge_threshold)
    return image_metrics_pil(image_path, alpha_threshold, gradient_edge_threshold)


def analyze_rendered_views(
    row: Dict[str, str],
    render_result: Dict[str, Any],
    args: argparse.Namespace,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    path = row.get("path", "")
    relative_path = row.get("relative_path", path)
    image_paths = [str(image_path) for image_path in render_result.get("images", [])]
    view_rows: List[Dict[str, Any]] = []
    metrics_by_view: List[Dict[str, Any]] = []

    for image_path in image_paths:
        view_name = Path(image_path).stem.rsplit("_normal_", 1)[-1]
        metrics = image_metrics(image_path, args.alpha_threshold, args.gradient_edge_threshold)
        view_row = {
            "path": path,
            "relative_path": relative_path,
            "view": view_name,
            "image_path": image_path,
            "error": metrics.get("error", ""),
        }
        view_row.update(metrics)
        view_rows.append(view_row)
        if metrics.get("readable"):
            metrics_by_view.append(metrics)

    visible_views = [item for item in metrics_by_view if safe_int(item.get("object_pixel_count")) >= args.min_object_pixels and safe_float(item.get("object_pixel_ratio")) >= args.min_object_ratio]

    object_ratios = [safe_float(item.get("object_pixel_ratio")) for item in visible_views]
    gradient_means = [safe_float(item.get("gradient_mean")) for item in visible_views]
    gradient_p95_values = [safe_float(item.get("gradient_p95")) for item in visible_views]
    laplacian_vars = [safe_float(item.get("laplacian_var")) for item in visible_views]
    entropies = [safe_float(item.get("entropy")) for item in visible_views]
    unique_bins = [safe_float(item.get("unique_bins")) for item in visible_views]
    color_ranges = [safe_float(item.get("color_range_mean")) for item in visible_views]

    def mean(values: Sequence[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    def minimum(values: Sequence[float]) -> float:
        return round(min(values), 6) if values else 0.0

    laplacian_mean = mean(laplacian_vars)
    gradient_mean = mean(gradient_means)
    gradient_p95_mean = mean(gradient_p95_values)
    entropy_mean = mean(entropies)
    unique_bins_mean = mean(unique_bins)
    color_range_mean = mean(color_ranges)

    detail_score = 100.0 * (
        0.40 * clamp(gradient_mean / max(args.good_gradient_mean, 1e-6))
        + 0.30 * clamp(entropy_mean / max(args.good_entropy, 1e-6))
        + 0.30 * clamp(unique_bins_mean / max(args.good_unique_bins, 1e-6))
    )
    sharpness_score = 100.0 * (
        0.60 * clamp(math.log1p(laplacian_mean) / max(math.log1p(args.good_laplacian_var), 1e-6))
        + 0.40 * clamp(gradient_p95_mean / max(args.good_gradient_p95, 1e-6))
    )
    visibility_score = 100.0 * clamp(len(visible_views) / max(args.min_visible_views, 1))
    geometry_signal_score = round(0.45 * detail_score + 0.45 * sharpness_score + 0.10 * visibility_score, 3)

    flags: List[str] = []
    if render_result.get("status") in {"failed", "skipped_no_blender"}:
        flags.append("normal_render_failed")
    if len(visible_views) < args.min_visible_views:
        flags.append("too_few_visible_normal_views")
    if object_ratios and minimum(object_ratios) < args.min_object_ratio:
        flags.append("small_object_in_normal_render")
    if laplacian_mean < args.min_laplacian_var:
        flags.append("normal_not_sharp")
    if gradient_mean < args.min_gradient_mean:
        flags.append("normal_low_gradient_detail")
    if entropy_mean < args.min_entropy:
        flags.append("normal_low_entropy")
    if unique_bins_mean < args.min_unique_bins:
        flags.append("normal_low_variation")
    if color_range_mean < args.min_color_range:
        flags.append("normal_flat_color_range")

    if "normal_render_failed" in flags:
        action = "render_failed"
    elif len(visible_views) < args.min_visible_views:
        action = "review_visibility"
    elif {"normal_low_gradient_detail", "normal_low_entropy", "normal_low_variation"}.issubset(set(flags)):
        action = "weak_3d_geometry_signal"
    elif flags:
        action = "review_normal_quality"
    else:
        action = "normal_pass"

    asset_row: Dict[str, Any] = {
        "path": path,
        "relative_path": relative_path,
        "status": row.get("status", ""),
        "lod": row.get("lod", ""),
        "face_count": row.get("face_count", ""),
        "vertex_count": row.get("vertex_count", ""),
        "image_count": row.get("image_count", ""),
        "texture_count": row.get("texture_count", ""),
        "extracted_texture_count": row.get("extracted_texture_count", ""),
        "ai_score": row.get("ai_score", ""),
        "ai_risk": row.get("ai_risk", ""),
        "candidate_reasons": row.get("candidate_reasons", "[]"),
        "render_status": render_result.get("status", "not_rendered"),
        "render_dir": str(Path(image_paths[0]).parent) if image_paths else "",
        "render_images": json.dumps(image_paths, ensure_ascii=False),
        "visible_view_count": len(visible_views),
        "object_pixel_ratio_mean": mean(object_ratios),
        "object_pixel_ratio_min": minimum(object_ratios),
        "normal_gradient_mean": gradient_mean,
        "normal_gradient_p95_mean": gradient_p95_mean,
        "normal_laplacian_var_mean": laplacian_mean,
        "normal_entropy_mean": entropy_mean,
        "normal_unique_bins_mean": unique_bins_mean,
        "normal_color_range_mean": color_range_mean,
        "normal_detail_score": round(detail_score, 3),
        "normal_sharpness_score": round(sharpness_score, 3),
        "geometry_signal_score": geometry_signal_score,
        "normal_quality_action": action,
        "normal_flags": json.dumps(flags, ensure_ascii=False),
        "render_error": "; ".join(str(error) for error in render_result.get("errors", [])),
    }
    return asset_row, view_rows


def summarize(
    candidates: Sequence[Dict[str, str]],
    rendered_rows: Sequence[Dict[str, str]],
    asset_rows: Sequence[Dict[str, Any]],
    view_rows: Sequence[Dict[str, Any]],
    args: argparse.Namespace,
    started_at: float,
) -> Dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    for row in candidates:
        for reason in parse_jsonish(row.get("candidate_reasons", ""), []):
            reason_counts[str(reason)] += 1

    action_counts = Counter(str(row.get("normal_quality_action", "not_rendered")) for row in asset_rows)
    render_counts = Counter(str(row.get("render_status", "not_rendered")) for row in asset_rows)
    folder_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for row in asset_rows:
        folder = asset_folder(str(row.get("relative_path", "")))
        folder_counts[folder]["asset_count"] += 1
        folder_counts[folder][str(row.get("normal_quality_action", "not_rendered"))] += 1

    return {
        "source_assets_csv": args.assets_csv,
        "source_issues_csv": args.issues_csv,
        "candidate_count": len(candidates),
        "render_selected_count": len(rendered_rows),
        "rendered_asset_count": len(asset_rows),
        "rendered_view_count": len(view_rows),
        "candidate_reason_counts": dict(reason_counts.most_common()),
        "normal_quality_action_counts": dict(action_counts.most_common()),
        "render_status_counts": dict(render_counts.most_common()),
        "folder_action_counts": {folder: dict(counts) for folder, counts in sorted(folder_counts.items())},
        "thresholds": {
            "max_texture_count": args.max_texture_count,
            "min_visible_views": args.min_visible_views,
            "min_object_pixels": args.min_object_pixels,
            "min_object_ratio": args.min_object_ratio,
            "min_laplacian_var": args.min_laplacian_var,
            "min_gradient_mean": args.min_gradient_mean,
            "min_entropy": args.min_entropy,
            "min_unique_bins": args.min_unique_bins,
            "min_color_range": args.min_color_range,
        },
        "pil_available": PIL_AVAILABLE,
        "numpy_available": NUMPY_AVAILABLE,
        "elapsed_sec": round(time.time() - started_at, 3),
    }


def render_summary_md(summary: Dict[str, Any], asset_rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Normal Render Audit Summary",
        "",
        f"- candidates: {summary['candidate_count']}",
        f"- selected for render: {summary['render_selected_count']}",
        f"- rendered assets analyzed: {summary['rendered_asset_count']}",
        f"- rendered normal views analyzed: {summary['rendered_view_count']}",
        f"- render status counts: {summary['render_status_counts']}",
        f"- normal quality action counts: {summary['normal_quality_action_counts']}",
        f"- candidate reason counts: {summary['candidate_reason_counts']}",
        f"- PIL available: {summary['pil_available']}",
        f"- numpy available: {summary['numpy_available']}",
        f"- elapsed_sec: {summary['elapsed_sec']}",
        "",
        "## Thresholds",
        "",
    ]
    for key, value in summary["thresholds"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Top Weak Geometry Signals",
            "",
            "| action | score | detail | sharpness | visible | textures | faces | asset | flags |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    weak_rows = sorted(
        asset_rows,
        key=lambda item: (
            str(item.get("normal_quality_action")) != "weak_3d_geometry_signal",
            safe_float(item.get("geometry_signal_score")),
            str(item.get("relative_path", "")),
        ),
    )
    for row in weak_rows[:100]:
        lines.append(
            f"| {row.get('normal_quality_action', '')} | {row.get('geometry_signal_score', '')} | "
            f"{row.get('normal_detail_score', '')} | {row.get('normal_sharpness_score', '')} | "
            f"{row.get('visible_view_count', '')} | {row.get('extracted_texture_count', '')} | "
            f"{row.get('face_count', '')} | `{row.get('relative_path', row.get('path', ''))}` | "
            f"`{row.get('normal_flags', '[]')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> None:
    started_at = time.time()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.select_only and not PIL_AVAILABLE:
        raise SystemExit("Missing required image metric dependency: Pillow")

    rows = read_csv(Path(args.assets_csv))
    issue_names = DEFAULT_PROBLEM_ISSUES if args.problem_issues == "default" else parse_csv_set(args.problem_issues)
    issue_map = load_validation_issue_map(args.issues_csv, issue_names, args.include_all_validation_issues)
    problem_statuses = parse_csv_set(args.problem_statuses)
    candidates = select_candidates(rows, issue_map, args.max_texture_count, problem_statuses, not args.no_include_ai)
    write_csv(out_dir / "normal_candidates.csv", candidates, CANDIDATE_FIELDS)

    render_rows = [] if args.select_only else choose_render_rows(candidates, args)
    write_csv(out_dir / "normal_render_selection.csv", render_rows, CANDIDATE_FIELDS)

    asset_rows: List[Dict[str, Any]] = []
    view_rows: List[Dict[str, Any]] = []
    if render_rows:
        render_results = render_normal_views(render_rows, args, out_dir)
        for row in render_rows:
            result = render_results.get(row.get("path", ""), {"status": "not_rendered", "images": [], "errors": []})
            asset_result, view_result_rows = analyze_rendered_views(row, result, args)
            asset_rows.append(asset_result)
            view_rows.extend(view_result_rows)

    write_csv(out_dir / "normal_audit_assets.csv", asset_rows, ASSET_FIELDS)
    write_csv(out_dir / "normal_audit_views.csv", view_rows, VIEW_FIELDS)

    summary = summarize(candidates, render_rows, asset_rows, view_rows, args, started_at)
    with (out_dir / "normal_audit_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    with (out_dir / "normal_audit_summary.md").open("w", encoding="utf-8") as handle:
        handle.write(render_summary_md(summary, asset_rows))

    print("===== normal render audit =====")
    print(f"candidates: {summary['candidate_count']}")
    print(f"selected_for_render: {summary['render_selected_count']}")
    print(f"render_status_counts: {summary['render_status_counts']}")
    print(f"normal_quality_action_counts: {summary['normal_quality_action_counts']}")
    print(f"report_dir: {out_dir}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render normal-view images for low-texture/problem GLB assets and score geometric detail")
    parser.add_argument("--assets-csv", required=True, help="assets.csv produced by glb_quality_audit.py")
    parser.add_argument("--issues-csv", default="", help="Optional deep_validation_issues.csv")
    parser.add_argument("--out-dir", required=True, help="Output directory for normal render audit reports")
    parser.add_argument("--select-only", action="store_true", help="Only write candidate CSVs; skip Blender rendering")
    parser.add_argument("--max-texture-count", type=int, default=4, help="Select assets with extracted_texture_count <= this value")
    parser.add_argument("--problem-statuses", default="rejected", help="Comma-separated asset statuses treated as existing problems")
    parser.add_argument("--problem-issues", default="default", help="Comma-separated validation issue names, or 'default'")
    parser.add_argument("--include-all-validation-issues", action="store_true", help="Treat every issue in --issues-csv as a problem signal")
    parser.add_argument("--no-include-ai", action="store_true", help="Do not add static AI candidates to the render set")
    parser.add_argument("--max-render-assets", type=int, default=100, help="Maximum assets to render; use 0 for no cap")
    parser.add_argument("--selection-order", choices=("priority", "path", "random"), default="priority", help="Order used before applying --max-render-assets")
    parser.add_argument("--sample-seed", type=int, default=42, help="Random seed when --selection-order=random")
    parser.add_argument("--overwrite", action="store_true", help="Re-render even if all expected normal images already exist")
    parser.add_argument("--blender-path", default=os.environ.get("BLENDER_PATH"), help="Blender executable path")
    parser.add_argument("--render-size", type=int, default=512, help="Square normal render size")
    parser.add_argument("--render-engine", default="BLENDER_EEVEE_NEXT", help="Blender render engine")
    parser.add_argument("--render-timeout-sec", type=int, default=90, help="Per-asset render timeout budget used to build total timeout")
    parser.add_argument("--alpha-threshold", type=int, default=8, help="Alpha threshold for model mask extraction")
    parser.add_argument("--gradient-edge-threshold", type=float, default=12.0, help="Internal edge threshold for view-level diagnostics")
    parser.add_argument("--min-visible-views", type=int, default=3, help="Minimum views with enough visible model pixels")
    parser.add_argument("--min-object-pixels", type=int, default=512, help="Minimum visible object pixels per valid view")
    parser.add_argument("--min-object-ratio", type=float, default=0.005, help="Minimum object area ratio per valid view")
    parser.add_argument("--min-laplacian-var", type=float, default=4.0, help="Warn below this mean Laplacian variance")
    parser.add_argument("--min-gradient-mean", type=float, default=1.0, help="Warn below this mean normal gradient")
    parser.add_argument("--min-entropy", type=float, default=1.5, help="Warn below this mean quantized color entropy")
    parser.add_argument("--min-unique-bins", type=float, default=8.0, help="Warn below this mean count of normal color bins")
    parser.add_argument("--min-color-range", type=float, default=8.0, help="Warn below this mean p5-p95 normal color range")
    parser.add_argument("--good-laplacian-var", type=float, default=30.0, help="Reference value for 100-point sharpness score")
    parser.add_argument("--good-gradient-mean", type=float, default=8.0, help="Reference value for 100-point detail score")
    parser.add_argument("--good-gradient-p95", type=float, default=30.0, help="Reference p95 gradient for 100-point sharpness score")
    parser.add_argument("--good-entropy", type=float, default=4.0, help="Reference entropy for 100-point detail score")
    parser.add_argument("--good-unique-bins", type=float, default=64.0, help="Reference unique bins for 100-point detail score")
    args = parser.parse_args(argv)
    if args.max_texture_count < 0:
        parser.error("--max-texture-count must be non-negative")
    if args.max_render_assets < 0:
        parser.error("--max-render-assets must be >= 0")
    if args.render_size <= 0:
        parser.error("--render-size must be positive")
    if args.min_visible_views <= 0:
        parser.error("--min-visible-views must be positive")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    run(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
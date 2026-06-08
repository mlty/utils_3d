#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GLB/glTF quality audit with optional six-view render and LLM sampling.

This script is meant to replace one-off Blender/VLM checks for first-pass local
acceptance. It parses the GLB container and glTF JSON directly, so it can run on
CPU without Blender or GPU models. When requested, it can also use local Blender
to render front/back/left/right/top/bottom PNGs into each asset folder's
``renders/`` directory, then sample assets and call an OpenAI-compatible ghc-api
vision endpoint for visual quality review.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import importlib
import io
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote, unquote_to_bytes, urlparse

try:
    Image = importlib.import_module("PIL.Image")
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False


GLB_MAGIC = b"glTF"
GLB_VERSION = 2
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BIN_CHUNK = 0x004E4942

DEFAULT_MODEL_EXTS = {".glb"}
SUPPORTED_MODEL_EXTS = {".glb", ".gltf"}
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

COMPONENT_TYPE_BYTES = {
    5120: 1,  # BYTE
    5121: 1,  # UNSIGNED_BYTE
    5122: 2,  # SHORT
    5123: 2,  # UNSIGNED_SHORT
    5125: 4,  # UNSIGNED_INT
    5126: 4,  # FLOAT
}
ACCESSOR_TYPE_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}
PRIMITIVE_MODES = {
    0: "POINTS",
    1: "LINES",
    2: "LINE_LOOP",
    3: "LINE_STRIP",
    4: "TRIANGLES",
    5: "TRIANGLE_STRIP",
    6: "TRIANGLE_FAN",
}

AI_KEYWORDS = {
    "ai",
    "aigc",
    "genai",
    "ai_generated",
    "ai-generated",
    "generated_by_ai",
    "generatedbyai",
    "text_to_3d",
    "text-to-3d",
    "textto3d",
    "txt2_3d",
    "txt23d",
    "txt2img",
    "stable_diffusion",
    "midjourney",
    "meshy",
    "tripo",
    "hunyuan",
    "hunyuan3d",
    "rodin",
    "luma",
    "kaedim",
    "3dfy",
    "scenario",
    "混元",
    "文生3d",
    "文生三维",
    "生成式",
    "人工智能",
}

GORE_KEYWORDS = {
    "blood",
    "bloody",
    "gore",
    "gory",
    "corpse",
    "dead_body",
    "severed",
    "dismember",
    "wound",
    "viscera",
    "organ",
    "flesh",
    "血",
    "血腥",
    "流血",
    "尸体",
    "尸块",
    "断肢",
    "伤口",
    "内脏",
    "肢解",
}
VIOLENCE_KEYWORDS = {
    "weapon",
    "gun",
    "rifle",
    "pistol",
    "knife",
    "sword",
    "axe",
    "bomb",
    "bullet",
    "grenade",
    "kill",
    "murder",
    "violent",
    "violence",
    "武器",
    "枪",
    "刀",
    "剑",
    "斧",
    "炸弹",
    "子弹",
    "暴力",
    "杀戮",
}

AI_STRONG_KEYWORDS = {
    "aigc",
    "genai",
    "ai_generated",
    "ai-generated",
    "generated_by_ai",
    "generatedbyai",
    "text_to_3d",
    "text-to-3d",
    "textto3d",
    "txt2_3d",
    "txt23d",
    "meshy",
    "tripo",
    "hunyuan",
    "hunyuan3d",
    "rodin",
    "luma",
    "kaedim",
    "3dfy",
    "混元",
    "文生3d",
    "文生三维",
}
AI_MEDIUM_KEYWORDS = {
    "stable_diffusion",
    "midjourney",
    "txt2img",
    "scenario",
    "生成式",
    "人工智能",
}

REJECT_REASON_DETAILS = {
    "missing_file": (
        "文件缺失",
        "输入清单里的模型路径不存在，无法验收。",
        "回源补齐文件，或从输入清单中移除该条。",
    ),
    "cannot_parse_or_open": (
        "无法解析/打开",
        "GLB/glTF 容器或 JSON 结构无法被解析。",
        "用 Blender 或 glTF validator 重新导出，确认文件不是损坏或截断的。",
    ),
    "empty_file": (
        "空文件",
        "文件大小为 0 或没有有效内容。",
        "重新下载/导出该资产。",
    ),
    "invalid_gltf_references": (
        "glTF 引用错误",
        "bufferView、accessor、mesh、material、texture 或 image 存在越界/缺失引用。",
        "回到源工程修复引用后重新导出 GLB。",
    ),
    "missing_external_images": (
        "外部贴图缺失",
        "glTF 引用了外部图片，但本地找不到对应贴图。",
        "补齐贴图文件，或导出为内嵌贴图 GLB。",
    ),
    "unreadable_images": (
        "贴图不可读",
        "图片文件存在但格式无法识别或无法读取。",
        "重新保存贴图为 PNG/JPG/WebP 等常见格式。",
    ),
    "no_mesh": (
        "没有 Mesh",
        "文件可解析，但没有可渲染的 mesh。",
        "确认导出设置包含 mesh 对象。",
    ),
    "no_primitive": (
        "没有 Primitive",
        "mesh 下没有 primitive，无法形成可渲染几何。",
        "重新导出模型几何。",
    ),
    "too_few_faces": (
        "面数过低",
        "三角面数量低于验收下限，通常是空壳或导出异常。",
        "检查模型是否缺几何，必要时重新导出。",
    ),
    "too_many_faces": (
        "面数过高",
        "三角面数量超过验收上限，会带来加载、渲染和存储风险。",
        "做减面/LOD，或把高模作为源资产，交付实时资产时使用优化版本。",
    ),
    "degenerate_bounds": (
        "包围盒退化",
        "模型空间尺寸接近 0，通常是几何退化或导出尺度异常。",
        "检查源模型尺度和变换，重新应用变换后导出。",
    ),
    "textures_without_uv": (
        "贴图缺 UV",
        "材质使用了贴图，但对应 primitive 缺少 TEXCOORD，贴图无法正确映射。",
        "补 UV 后重新导出；如果不需要贴图，应移除材质里的贴图引用。",
    ),
    "no_texture": (
        "缺少贴图",
        "当前规则要求必须有贴图，但资产没有 image/texture。",
        "补齐贴图，或确认该批次允许纯材质模型后去掉 --require-textures。",
    ),
    "no_pbr": (
        "缺少 PBR 材质",
        "当前规则要求 PBR，但材质缺少 pbrMetallicRoughness 等 PBR 字段。",
        "按 glTF PBR 规范重新设置材质并导出。",
    ),
    "ai_asset_suspect": (
        "疑似 AI 资产",
        "路径、元数据、节点、材质或贴图命名命中 AI/文生 3D 工具关键词。",
        "补充来源证明；如果业务不允许 AI 资产，建议剔除或转人工复核。",
    ),
    "gore_keyword_suspect": (
        "疑似血腥违规",
        "路径或模型元数据命中血腥/尸体/伤口等关键词。",
        "优先人工检查六视角渲染图；确认命中后剔除。",
    ),
    "violence_keyword_suspect": (
        "疑似暴力/武器",
        "路径或模型元数据命中武器、枪、刀、爆炸等关键词。",
        "按业务策略判断是否允许；不允许时剔除，允许时转人工确认。",
    ),
}

REJECT_DETAIL_FIELDS = [
    "path",
    "relative_path",
    "status",
    "lod",
    "face_count",
    "file_size_mb",
    "reject_reasons",
    "reason_details",
    "evidence",
    "suggested_action",
    "errors",
    "warnings",
    "review_reasons",
    "ai_score",
    "ai_risk",
    "ai_markers",
    "ai_evidence",
    "gore_markers",
    "violence_markers",
    "texture_extract_status",
    "extracted_texture_count",
    "render_status",
    "llm_decision",
    "llm_is_ai_asset",
]

AI_CANDIDATE_FIELDS = [
    "path",
    "relative_path",
    "status",
    "ai_score",
    "ai_risk",
    "ai_suspect",
    "ai_markers",
    "ai_evidence",
    "ai_review_action",
    "llm_status",
    "llm_decision",
    "llm_is_ai_asset",
    "llm_aesthetic_score",
    "llm_unreasonable_parts",
    "reject_reasons",
    "review_reasons",
]

CSV_FIELDS = [
    "path",
    "relative_path",
    "extension",
    "exists",
    "parse_ok",
    "status",
    "lod",
    "file_size_mb",
    "face_count",
    "vertex_count",
    "mesh_count",
    "primitive_count",
    "material_count",
    "texture_count",
    "image_count",
    "embedded_image_count",
    "external_image_count",
    "has_textures",
    "has_pbr",
    "has_uvs",
    "has_normals",
    "has_animation",
    "has_skin",
    "missing_external_images",
    "unreadable_images",
    "invalid_references",
    "ai_suspect",
    "ai_markers",
    "ai_score",
    "ai_risk",
    "ai_evidence",
    "ai_review_action",
    "content_risk",
    "gore_markers",
    "violence_markers",
    "reject_reasons",
    "review_reasons",
    "errors",
    "warnings",
    "texture_extract_status",
    "texture_extract_dir",
    "extracted_texture_count",
    "extracted_textures",
    "texture_extract_errors",
    "render_status",
    "render_dir",
    "render_images",
    "llm_sampled",
    "llm_status",
    "llm_decision",
    "llm_is_ai_asset",
    "llm_aesthetic_score",
    "llm_violence_gore_risk",
    "llm_unreasonable_parts",
]


@dataclass(frozen=True)
class AuditConfig:
    root: Optional[str]
    input_list: Optional[str]
    out_dir: str
    include_exts: Tuple[str, ...]
    expected_count: Optional[int]
    low_faces: int
    high_faces: int
    min_faces: int
    max_faces: int
    max_file_mb: float
    require_textures: bool
    require_pbr: bool
    reject_ai: bool
    reject_violence_keywords: bool
    inspect_images: bool
    min_texture_size: int
    max_texture_size: int
    workers: int
    list_path_column: int
    sample_limit: Optional[int]
    max_examples: int
    extract_textures: bool
    texture_overwrite: bool
    texture_dir_name: str
    render_six_views: bool
    render_overwrite: bool
    blender_path: Optional[str]
    render_size: int
    render_engine: str
    render_timeout_sec: int
    llm_review: bool
    llm_sample_rate: float
    llm_sample_seed: int
    llm_max_assets: Optional[int]
    llm_workers: int
    ghc_api_url: Optional[str]
    ghc_api_key_env: str
    ghc_api_model: str
    ghc_api_timeout_sec: int
    ghc_api_temperature: float


@dataclass
class GltfContainer:
    gltf: Dict[str, Any]
    base_dir: str
    container_type: str
    bin_chunks: List[Dict[str, int]]
    warnings: List[str]


def normalize_exts(raw: str) -> Tuple[str, ...]:
    exts = []
    for part in raw.split(","):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        exts.append(ext)
    return tuple(sorted(set(exts)))


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_relpath(path: Path, root: Optional[Path]) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return os.path.relpath(str(path), str(root))


def is_remote_uri(uri: str) -> bool:
    scheme = urlparse(uri).scheme.lower()
    return scheme in {"http", "https"}


def is_data_uri(uri: str) -> bool:
    return uri.startswith("data:")


def uri_to_local_path(base_dir: str, uri: str) -> Optional[str]:
    if is_remote_uri(uri) or is_data_uri(uri):
        return None
    parsed = urlparse(uri)
    if parsed.scheme not in {"", "file"}:
        return None
    raw_path = unquote(parsed.path if parsed.scheme == "file" else uri)
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.normpath(os.path.join(base_dir, raw_path))


def collect_files(config: AuditConfig) -> Tuple[List[str], List[str]]:
    root = Path(config.root).expanduser().resolve() if config.root else None
    discovered: List[str] = []
    missing: List[str] = []
    seen = set()

    if config.input_list:
        list_path = Path(config.input_list).expanduser().resolve()
        list_base = list_path.parent
        with list_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                columns = line.split("\t") if "\t" in line else line.split()
                if config.list_path_column >= len(columns):
                    missing.append(line)
                    continue
                candidate = Path(columns[config.list_path_column]).expanduser()
                if not candidate.is_absolute():
                    candidate = (root / candidate) if root else (list_base / candidate)
                candidate = candidate.resolve()
                key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if candidate.exists():
                    discovered.append(key)
                else:
                    missing.append(key)
    elif root:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in config.include_exts:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            discovered.append(key)

    discovered.sort()
    missing.sort()
    if config.sample_limit is not None:
        discovered = discovered[: config.sample_limit]
    return discovered, missing


def parse_glb(path: str) -> GltfContainer:
    warnings: List[str] = []
    file_size = os.path.getsize(path)
    if file_size < 20:
        raise ValueError("GLB file is too small")

    json_bytes: Optional[bytes] = None
    bin_chunks: List[Dict[str, int]] = []
    with open(path, "rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            raise ValueError("Cannot read GLB header")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != GLB_MAGIC:
            raise ValueError("Invalid GLB magic")
        if version != GLB_VERSION:
            raise ValueError(f"Unsupported GLB version {version}")
        if declared_length > file_size:
            raise ValueError(
                f"GLB declared length {declared_length} exceeds file size {file_size}"
            )
        if declared_length != file_size:
            warnings.append(
                f"GLB declared length {declared_length} differs from file size {file_size}"
            )

        offset = 12
        chunk_index = 0
        while offset + 8 <= declared_length:
            handle.seek(offset)
            chunk_header = handle.read(8)
            if len(chunk_header) != 8:
                raise ValueError("Cannot read GLB chunk header")
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            data_offset = offset + 8
            data_end = data_offset + chunk_length
            if data_end > declared_length or data_end > file_size:
                raise ValueError("GLB chunk extends beyond file length")
            if chunk_index == 0 and chunk_type != GLB_JSON_CHUNK:
                raise ValueError("First GLB chunk is not JSON")
            if chunk_type == GLB_JSON_CHUNK:
                if json_bytes is not None:
                    warnings.append("Multiple JSON chunks found; using the first one")
                else:
                    handle.seek(data_offset)
                    json_bytes = handle.read(chunk_length)
            elif chunk_type == GLB_BIN_CHUNK:
                bin_chunks.append({"offset": data_offset, "length": chunk_length})
            else:
                warnings.append(f"Unknown GLB chunk type {chunk_type}")
            offset = data_end
            chunk_index += 1

        if offset != declared_length:
            warnings.append("GLB chunks do not align exactly with declared length")

    if json_bytes is None:
        raise ValueError("Missing GLB JSON chunk")
    json_text = json_bytes.decode("utf-8").rstrip("\x00 \t\r\n")
    gltf = json.loads(json_text)
    return GltfContainer(
        gltf=gltf,
        base_dir=os.path.dirname(path),
        container_type="glb",
        bin_chunks=bin_chunks,
        warnings=warnings,
    )


def parse_gltf(path: str) -> GltfContainer:
    with open(path, "r", encoding="utf-8") as handle:
        gltf = json.load(handle)
    return GltfContainer(
        gltf=gltf,
        base_dir=os.path.dirname(path),
        container_type="gltf",
        bin_chunks=[],
        warnings=[],
    )


def parse_container(path: str) -> GltfContainer:
    ext = Path(path).suffix.lower()
    if ext == ".glb":
        return parse_glb(path)
    if ext == ".gltf":
        return parse_gltf(path)
    raise ValueError(f"Unsupported extension {ext}; only .glb/.gltf are supported")


def decode_data_uri(uri: str, limit_bytes: int = 64 * 1024 * 1024) -> Tuple[bytes, str]:
    header, _, payload = uri.partition(",")
    if not payload:
        raise ValueError("Malformed data URI")
    media_type = header[5:].split(";", 1)[0] if header.startswith("data:") else ""
    if ";base64" in header:
        data = base64.b64decode(payload, validate=True)
    else:
        data = unquote_to_bytes(payload)
    if len(data) > limit_bytes:
        raise ValueError("Data URI image is too large to inspect")
    return data, media_type


def read_buffer_view_bytes(
    model_path: str,
    container: GltfContainer,
    buffer_view_index: int,
    limit_bytes: int = 64 * 1024 * 1024,
) -> bytes:
    gltf = container.gltf
    buffer_views = as_list(gltf.get("bufferViews"))
    buffers = as_list(gltf.get("buffers"))
    if buffer_view_index < 0 or buffer_view_index >= len(buffer_views):
        raise ValueError(f"Invalid bufferView index {buffer_view_index}")
    buffer_view = as_dict(buffer_views[buffer_view_index])
    buffer_index = int(buffer_view.get("buffer", 0))
    if buffer_index < 0 or buffer_index >= len(buffers):
        raise ValueError(f"Invalid buffer index {buffer_index}")
    byte_offset = int(buffer_view.get("byteOffset", 0))
    byte_length = int(buffer_view.get("byteLength", 0))
    if byte_length > limit_bytes:
        raise ValueError("Embedded image is too large to inspect")

    buffer_def = as_dict(buffers[buffer_index])
    uri = buffer_def.get("uri")
    if container.container_type == "glb" and not uri and buffer_index == 0:
        if not container.bin_chunks:
            raise ValueError("Missing GLB BIN chunk")
        bin_chunk = container.bin_chunks[0]
        if byte_offset + byte_length > bin_chunk["length"]:
            raise ValueError("bufferView exceeds GLB BIN chunk")
        with open(model_path, "rb") as handle:
            handle.seek(bin_chunk["offset"] + byte_offset)
            return handle.read(byte_length)

    if isinstance(uri, str) and is_data_uri(uri):
        data, _ = decode_data_uri(uri)
        if byte_offset + byte_length > len(data):
            raise ValueError("bufferView exceeds data URI buffer")
        return data[byte_offset : byte_offset + byte_length]

    if isinstance(uri, str):
        local_path = uri_to_local_path(container.base_dir, uri)
        if not local_path:
            raise ValueError("Cannot read remote or unsupported buffer URI")
        with open(local_path, "rb") as handle:
            handle.seek(byte_offset)
            return handle.read(byte_length)

    raise ValueError("Cannot resolve bufferView bytes")


def image_magic_name(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "tiff"
    if data.startswith(b"\x76\x2f\x31\x01"):
        return "exr"
    return "unknown"


def inspect_image_bytes(data: bytes) -> Dict[str, Any]:
    info: Dict[str, Any] = {"magic": image_magic_name(data), "readable": False}
    if info["magic"] == "unknown":
        return info
    if PIL_AVAILABLE and Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                info["width"], info["height"] = image.size
                info["mode"] = image.mode
                image.verify()
            info["readable"] = True
        except Exception as exc:
            info["error"] = str(exc)
    else:
        info["readable"] = True
    return info


def inspect_image_file(path: str, inspect_images: bool) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": path,
        "exists": os.path.exists(path),
        "readable": False,
    }
    if not info["exists"]:
        return info
    try:
        info["size_bytes"] = os.path.getsize(path)
        if not inspect_images:
            info["readable"] = True
            return info
        with open(path, "rb") as handle:
            head = handle.read(32)
        info["magic"] = image_magic_name(head)
        if info["magic"] == "unknown":
            if not PIL_AVAILABLE and Path(path).suffix.lower() in IMAGE_EXTS:
                info["readable"] = True
                info["unchecked"] = True
            return info
        if inspect_images and PIL_AVAILABLE and Image is not None:
            with Image.open(path) as image:
                info["width"], info["height"] = image.size
                info["mode"] = image.mode
                image.verify()
        info["readable"] = True
    except Exception as exc:
        info["error"] = str(exc)
    return info


def iter_string_values(value: Any, limit: int = 5000) -> Iterable[str]:
    stack = [value]
    yielded = 0
    while stack and yielded < limit:
        current = stack.pop()
        if isinstance(current, str):
            yielded += 1
            yield current
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def keyword_matches(texts: Iterable[str], keywords: Sequence[str]) -> Dict[str, List[str]]:
    matches: Dict[str, List[str]] = defaultdict(list)
    normalized_texts = []
    for text in texts:
        if not text:
            continue
        normalized_texts.append(str(text).casefold())

    for keyword in sorted(set(keywords)):
        keyword_norm = keyword.casefold()
        if keyword_norm == "ai":
            pattern = re.compile(r"(?<![a-z0-9])ai(?![a-z0-9])", re.IGNORECASE)
        elif keyword_norm.isascii() and keyword_norm.replace("_", "").isalnum():
            escaped = re.escape(keyword_norm).replace("_", r"[-_ ]?")
            pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
        else:
            pattern = None

        for text in normalized_texts:
            hit = bool(pattern.search(text)) if pattern else keyword_norm in text
            if hit:
                example = text[:180]
                if example not in matches[keyword]:
                    matches[keyword].append(example)
    return {key: value[:5] for key, value in matches.items()}


def marker_evidence(markers: Any, limit: int = 8) -> List[str]:
    evidence: List[str] = []
    for keyword, examples in sorted(as_dict(markers).items()):
        example_list = as_list(examples)
        if example_list:
            evidence.append(f"{keyword}: {str(example_list[0])[:180]}")
        else:
            evidence.append(str(keyword))
        if len(evidence) >= limit:
            break
    return evidence


def ai_keyword_weight(keyword: str) -> int:
    normalized = keyword.casefold()
    if normalized in AI_STRONG_KEYWORDS:
        return 75
    if normalized in AI_MEDIUM_KEYWORDS:
        return 50
    if normalized == "ai":
        return 20
    return 35


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def update_ai_assessment(record: Dict[str, Any]) -> None:
    score = 0
    evidence: List[str] = []
    markers = as_dict(record.get("ai_markers"))
    for keyword, examples in sorted(markers.items()):
        weight = ai_keyword_weight(str(keyword))
        score += weight
        sample = as_list(examples)[0] if as_list(examples) else ""
        evidence.append(f"静态关键词命中 `{keyword}`: {str(sample)[:180]}")
    if len(markers) > 1:
        score += min(15, (len(markers) - 1) * 5)

    llm_answer = str(record.get("llm_is_ai_asset") or "").casefold()
    llm_response = as_dict(record.get("llm_response"))
    llm_ai = as_dict(llm_response.get("is_ai_asset"))
    confidence = max(0.0, min(1.0, safe_float(llm_ai.get("confidence"), 0.0)))
    llm_reason = str(llm_ai.get("reason") or "")[:240]
    if llm_answer == "yes":
        score += 70 + int(confidence * 20)
        evidence.append(f"LLM 视觉判断为 AI: confidence={confidence:.2f}; {llm_reason}")
    elif llm_answer == "uncertain":
        score += 25 + int(confidence * 10)
        evidence.append(f"LLM 视觉判断不确定: confidence={confidence:.2f}; {llm_reason}")
    elif llm_answer == "no" and evidence:
        evidence.append(f"LLM 视觉判断暂未发现 AI 特征: confidence={confidence:.2f}; {llm_reason}")

    score = max(0, min(100, score))
    if score >= 75:
        risk = "high"
        action = "优先人工复核来源；若业务不允许 AI 资产，建议剔除或要求提供来源证明。"
    elif score >= 45:
        risk = "medium"
        action = "建议补跑六视角 LLM 复核，并检查 imgs/ 贴图和模型元数据。"
    elif score >= 20:
        risk = "low"
        action = "保留标记，抽样人工确认；短关键词命中不应单独作为拒收依据。"
    else:
        risk = "no_evidence"
        action = "未发现明确 AI 证据；仍可通过抽样 LLM/人工复核兜底。"

    record["ai_score"] = score
    record["ai_risk"] = risk
    record["ai_evidence"] = evidence[:12]
    record["ai_review_action"] = action


def count_faces_for_primitive(primitive: Dict[str, Any], accessors: List[Any]) -> Tuple[int, int, int]:
    mode = int(primitive.get("mode", 4))
    attributes = as_dict(primitive.get("attributes"))
    vertex_count = 0
    index_count = 0
    position_index = attributes.get("POSITION")
    if isinstance(position_index, int) and 0 <= position_index < len(accessors):
        vertex_count = int(as_dict(accessors[position_index]).get("count", 0))
    indices_index = primitive.get("indices")
    if isinstance(indices_index, int) and 0 <= indices_index < len(accessors):
        index_count = int(as_dict(accessors[indices_index]).get("count", 0))
    count = index_count or vertex_count
    if mode == 4:
        face_count = count // 3
    elif mode in {5, 6}:
        face_count = max(0, count - 2)
    else:
        face_count = 0
    return face_count, vertex_count, index_count


def classify_lod(face_count: int, low_faces: int, high_faces: int) -> str:
    if face_count < low_faces:
        return "low"
    if face_count <= high_faces:
        return "mid"
    return "high"


def collect_material_texture_slots(material: Dict[str, Any]) -> List[Tuple[str, int, int]]:
    slots: List[Tuple[str, int, int]] = []
    pbr = as_dict(material.get("pbrMetallicRoughness"))
    for field in ("baseColorTexture", "metallicRoughnessTexture"):
        texture_info = as_dict(pbr.get(field))
        if isinstance(texture_info.get("index"), int):
            slots.append((field, int(texture_info["index"]), int(texture_info.get("texCoord", 0))))
    for field in ("normalTexture", "occlusionTexture", "emissiveTexture"):
        texture_info = as_dict(material.get(field))
        if isinstance(texture_info.get("index"), int):
            slots.append((field, int(texture_info["index"]), int(texture_info.get("texCoord", 0))))
    return slots


MIME_EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
    "image/x-tga": ".tga",
    "image/vnd.radiance": ".hdr",
}


MAGIC_EXTENSION_MAP = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
    "gif": ".gif",
    "bmp": ".bmp",
    "tiff": ".tiff",
    "exr": ".exr",
}


def safe_file_stem(text: Any, fallback: str) -> str:
    stem = Path(str(text or "")).stem or fallback
    stem = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", stem).strip("._-")
    return stem[:80] or fallback


def extension_for_texture(label: Any, mime_type: Any = None, data: Optional[bytes] = None) -> str:
    if isinstance(mime_type, str):
        ext = MIME_EXTENSION_MAP.get(mime_type.lower())
        if ext:
            return ext
    suffix = Path(str(label or "")).suffix.lower()
    if suffix in IMAGE_EXTS:
        return suffix
    if data:
        return MAGIC_EXTENSION_MAP.get(image_magic_name(data), ".png")
    return ".png"


def write_extracted_texture(
    data: bytes,
    output_dir: Path,
    file_name: str,
    overwrite: bool,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    if not overwrite:
        base = output_path.stem
        suffix = output_path.suffix
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base}_{counter}{suffix}"
            counter += 1
    with output_path.open("wb") as writer:
        writer.write(data)
    return str(output_path)


def copy_extracted_texture(
    source_path: str,
    output_dir: Path,
    file_name: str,
    overwrite: bool,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    if not overwrite:
        base = output_path.stem
        suffix = output_path.suffix
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base}_{counter}{suffix}"
            counter += 1
    shutil.copy2(source_path, output_path)
    return str(output_path)


def extracted_texture_name(model_path: str, image_index: int, label: Any, ext: str) -> str:
    model_stem = safe_file_stem(Path(model_path).stem, "asset")
    image_stem = safe_file_stem(label, f"image_{image_index:03d}")
    return f"{model_stem}_image_{image_index:03d}_{image_stem}{ext}"


def validate_references(gltf: Dict[str, Any]) -> Tuple[List[str], Dict[str, int]]:
    invalid: List[str] = []
    stats: Dict[str, int] = defaultdict(int)
    buffers = as_list(gltf.get("buffers"))
    buffer_views = as_list(gltf.get("bufferViews"))
    accessors = as_list(gltf.get("accessors"))
    meshes = as_list(gltf.get("meshes"))
    materials = as_list(gltf.get("materials"))
    textures = as_list(gltf.get("textures"))
    images = as_list(gltf.get("images"))
    samplers = as_list(gltf.get("samplers"))

    for index, buffer_view in enumerate(buffer_views):
        view = as_dict(buffer_view)
        buffer_index = view.get("buffer", 0)
        if not isinstance(buffer_index, int) or not 0 <= buffer_index < len(buffers):
            invalid.append(f"bufferView[{index}] invalid buffer={buffer_index}")
            continue
        byte_length = int(view.get("byteLength", 0))
        byte_offset = int(view.get("byteOffset", 0))
        buffer_length = int(as_dict(buffers[buffer_index]).get("byteLength", 0))
        if byte_length <= 0:
            invalid.append(f"bufferView[{index}] has non-positive byteLength")
        if byte_offset < 0 or byte_offset + byte_length > buffer_length:
            invalid.append(f"bufferView[{index}] exceeds buffer[{buffer_index}]")

    for index, accessor in enumerate(accessors):
        acc = as_dict(accessor)
        component_type = acc.get("componentType")
        accessor_type = acc.get("type")
        count = int(acc.get("count", 0))
        if component_type not in COMPONENT_TYPE_BYTES:
            invalid.append(f"accessor[{index}] invalid componentType={component_type}")
            continue
        if accessor_type not in ACCESSOR_TYPE_COMPONENTS:
            invalid.append(f"accessor[{index}] invalid type={accessor_type}")
            continue
        if count < 0:
            invalid.append(f"accessor[{index}] has negative count")
        buffer_view_index = acc.get("bufferView")
        if buffer_view_index is None:
            if "sparse" not in acc:
                stats["accessor_without_bufferView"] += 1
            continue
        if not isinstance(buffer_view_index, int) or not 0 <= buffer_view_index < len(buffer_views):
            invalid.append(f"accessor[{index}] invalid bufferView={buffer_view_index}")
            continue
        view = as_dict(buffer_views[buffer_view_index])
        component_bytes = COMPONENT_TYPE_BYTES[component_type]
        component_count = ACCESSOR_TYPE_COMPONENTS[accessor_type]
        element_size = component_bytes * component_count
        byte_offset = int(acc.get("byteOffset", 0))
        stride = int(view.get("byteStride", element_size))
        view_length = int(view.get("byteLength", 0))
        required = byte_offset + element_size
        if count > 0:
            required = byte_offset + stride * (count - 1) + element_size
        if required > view_length:
            invalid.append(f"accessor[{index}] exceeds bufferView[{buffer_view_index}]")

    for mesh_index, mesh in enumerate(meshes):
        for prim_index, primitive in enumerate(as_list(as_dict(mesh).get("primitives"))):
            prim = as_dict(primitive)
            stats["primitive_count"] += 1
            material_index = prim.get("material")
            if material_index is not None and (
                not isinstance(material_index, int) or not 0 <= material_index < len(materials)
            ):
                invalid.append(f"mesh[{mesh_index}].primitive[{prim_index}] invalid material")
            indices_index = prim.get("indices")
            if indices_index is not None and (
                not isinstance(indices_index, int) or not 0 <= indices_index < len(accessors)
            ):
                invalid.append(f"mesh[{mesh_index}].primitive[{prim_index}] invalid indices")
            attributes = as_dict(prim.get("attributes"))
            if "POSITION" not in attributes:
                invalid.append(f"mesh[{mesh_index}].primitive[{prim_index}] missing POSITION")
            for attr_name, accessor_index in attributes.items():
                if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
                    invalid.append(
                        f"mesh[{mesh_index}].primitive[{prim_index}] invalid attribute {attr_name}"
                    )

    for texture_index, texture in enumerate(textures):
        tex = as_dict(texture)
        source = tex.get("source")
        sampler = tex.get("sampler")
        if source is not None and (
            not isinstance(source, int) or not 0 <= source < len(images)
        ):
            invalid.append(f"texture[{texture_index}] invalid source={source}")
        if sampler is not None and (
            not isinstance(sampler, int) or not 0 <= sampler < len(samplers)
        ):
            invalid.append(f"texture[{texture_index}] invalid sampler={sampler}")

    for image_index, image in enumerate(images):
        img = as_dict(image)
        buffer_view = img.get("bufferView")
        uri = img.get("uri")
        if buffer_view is not None and (
            not isinstance(buffer_view, int) or not 0 <= buffer_view < len(buffer_views)
        ):
            invalid.append(f"image[{image_index}] invalid bufferView={buffer_view}")
        if buffer_view is None and not uri:
            invalid.append(f"image[{image_index}] has neither uri nor bufferView")

    for material_index, material in enumerate(materials):
        for field, texture_index, _ in collect_material_texture_slots(as_dict(material)):
            if not 0 <= texture_index < len(textures):
                invalid.append(
                    f"material[{material_index}] {field} invalid texture={texture_index}"
                )

    return invalid, dict(stats)


def analyze_textures(
    model_path: str,
    container: GltfContainer,
    config: AuditConfig,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    gltf = container.gltf
    images = as_list(gltf.get("images"))
    textures = as_list(gltf.get("textures"))
    materials = as_list(gltf.get("materials"))
    meshes = as_list(gltf.get("meshes"))
    warnings: List[str] = []
    errors: List[str] = []

    stats: Dict[str, Any] = {
        "image_count": len(images),
        "texture_count": len(textures),
        "material_count": len(materials),
        "embedded_image_count": 0,
        "external_image_count": 0,
        "remote_image_count": 0,
        "data_uri_image_count": 0,
        "missing_external_images": [],
        "unreadable_images": [],
        "small_textures": [],
        "large_textures": [],
        "material_texture_slots": 0,
        "pbr_material_count": 0,
        "missing_uv_for_textures": [],
        "unused_image_count": 0,
        "texture_extract_status": "",
        "texture_extract_dir": "",
        "extracted_textures": [],
        "extracted_texture_count": 0,
        "texture_extract_errors": [],
    }

    extract_dir = Path(model_path).parent / config.texture_dir_name
    if config.extract_textures:
        stats["texture_extract_dir"] = str(extract_dir)

    texture_sources = set()
    for texture in textures:
        source = as_dict(texture).get("source")
        if isinstance(source, int):
            texture_sources.add(source)
    stats["unused_image_count"] = len([i for i in range(len(images)) if i not in texture_sources])

    for image_index, image in enumerate(images):
        img = as_dict(image)
        uri = img.get("uri")
        buffer_view = img.get("bufferView")
        mime_type = img.get("mimeType")
        label = img.get("name") or uri or f"image[{image_index}]"
        info: Dict[str, Any] = {}
        image_data: Optional[bytes] = None
        local_path_for_extract: Optional[str] = None
        try:
            if isinstance(uri, str) and is_remote_uri(uri):
                stats["remote_image_count"] += 1
                warnings.append(f"Remote image URI cannot be validated locally: {label}")
                continue
            if isinstance(uri, str) and is_data_uri(uri):
                stats["embedded_image_count"] += 1
                stats["data_uri_image_count"] += 1
                data, _ = decode_data_uri(uri)
                image_data = data
                info = inspect_image_bytes(data) if config.inspect_images else {"readable": True}
            elif isinstance(buffer_view, int):
                stats["embedded_image_count"] += 1
                data = read_buffer_view_bytes(model_path, container, buffer_view)
                image_data = data
                info = inspect_image_bytes(data) if config.inspect_images else {"readable": True}
            elif isinstance(uri, str):
                stats["external_image_count"] += 1
                local_path = uri_to_local_path(container.base_dir, uri)
                if not local_path:
                    warnings.append(f"Unsupported image URI: {label}")
                    continue
                local_path_for_extract = local_path
                if Path(uri).suffix.lower() not in IMAGE_EXTS:
                    warnings.append(f"Image URI has unusual extension: {label}")
                info = inspect_image_file(local_path, config.inspect_images)
                if not info.get("exists"):
                    stats["missing_external_images"].append(label)
                    errors.append(f"Missing external image: {label}")
                    continue
            else:
                errors.append(f"Image has no usable uri/bufferView: {label}")
                continue
        except (OSError, ValueError, binascii.Error) as exc:
            stats["unreadable_images"].append(label)
            errors.append(f"Unreadable image {label}: {exc}")
            continue

        if not info.get("readable", False):
            stats["unreadable_images"].append(label)
            errors.append(f"Unreadable image: {label}")
            continue

        if config.extract_textures:
            try:
                if image_data is not None:
                    ext = extension_for_texture(label, mime_type, image_data)
                    file_name = extracted_texture_name(model_path, image_index, label, ext)
                    saved_path = write_extracted_texture(image_data, extract_dir, file_name, config.texture_overwrite)
                elif local_path_for_extract:
                    ext = extension_for_texture(local_path_for_extract, mime_type, None)
                    file_name = extracted_texture_name(model_path, image_index, label or local_path_for_extract, ext)
                    saved_path = copy_extracted_texture(local_path_for_extract, extract_dir, file_name, config.texture_overwrite)
                else:
                    saved_path = ""
                if saved_path:
                    stats["extracted_textures"].append(saved_path)
            except Exception as exc:
                message = f"Texture extract failed: {label}: {exc}"
                stats["texture_extract_errors"].append(message)
                warnings.append(message)

        width = info.get("width")
        height = info.get("height")
        if isinstance(width, int) and isinstance(height, int):
            min_side = min(width, height)
            max_side = max(width, height)
            if min_side < config.min_texture_size:
                stats["small_textures"].append(f"{label}({width}x{height})")
                warnings.append(f"Texture too small: {label}({width}x{height})")
            if max_side > config.max_texture_size:
                stats["large_textures"].append(f"{label}({width}x{height})")
                warnings.append(f"Texture too large: {label}({width}x{height})")

    for material in materials:
        mat = as_dict(material)
        slots = collect_material_texture_slots(mat)
        stats["material_texture_slots"] += len(slots)
        if as_dict(mat.get("pbrMetallicRoughness")):
            stats["pbr_material_count"] += 1

    material_slots = {
        index: collect_material_texture_slots(as_dict(material))
        for index, material in enumerate(materials)
    }
    for mesh_index, mesh in enumerate(meshes):
        for prim_index, primitive in enumerate(as_list(as_dict(mesh).get("primitives"))):
            prim = as_dict(primitive)
            material_index = prim.get("material")
            if not isinstance(material_index, int):
                continue
            slots = material_slots.get(material_index, [])
            if not slots:
                continue
            attributes = as_dict(prim.get("attributes"))
            for field, _, tex_coord in slots:
                uv_name = f"TEXCOORD_{tex_coord}"
                if uv_name not in attributes:
                    stats["missing_uv_for_textures"].append(
                        f"mesh[{mesh_index}].primitive[{prim_index}] material[{material_index}] {field} needs {uv_name}"
                    )
    if stats["missing_uv_for_textures"]:
        errors.extend(stats["missing_uv_for_textures"])

    stats["has_textures"] = stats["texture_count"] > 0 or stats["image_count"] > 0
    stats["has_pbr"] = stats["pbr_material_count"] > 0
    if config.extract_textures:
        stats["extracted_texture_count"] = len(stats["extracted_textures"])
        if stats["image_count"] == 0:
            stats["texture_extract_status"] = "no_images"
        elif stats["texture_extract_errors"] and stats["extracted_textures"]:
            stats["texture_extract_status"] = "partial"
        elif stats["texture_extract_errors"]:
            stats["texture_extract_status"] = "failed"
        else:
            stats["texture_extract_status"] = "ok"
    return stats, warnings, errors


def analyze_geometry(gltf: Dict[str, Any], config: AuditConfig) -> Dict[str, Any]:
    meshes = as_list(gltf.get("meshes"))
    accessors = as_list(gltf.get("accessors"))
    total_faces = 0
    total_vertices = 0
    total_indices = 0
    primitive_count = 0
    mode_counter: Counter[str] = Counter()
    has_normals = False
    has_uvs = False
    position_accessor_indices = set()

    for mesh in meshes:
        for primitive in as_list(as_dict(mesh).get("primitives")):
            prim = as_dict(primitive)
            primitive_count += 1
            mode = int(prim.get("mode", 4))
            mode_counter[PRIMITIVE_MODES.get(mode, f"UNKNOWN_{mode}")] += 1
            face_count, vertex_count, index_count = count_faces_for_primitive(prim, accessors)
            total_faces += face_count
            total_vertices += vertex_count
            total_indices += index_count
            attributes = as_dict(prim.get("attributes"))
            has_normals = has_normals or "NORMAL" in attributes
            has_uvs = has_uvs or any(key.startswith("TEXCOORD_") for key in attributes)
            position_index = attributes.get("POSITION")
            if isinstance(position_index, int):
                position_accessor_indices.add(position_index)

    bbox_min: Optional[List[float]] = None
    bbox_max: Optional[List[float]] = None
    missing_bounds = 0
    for accessor_index in position_accessor_indices:
        if not 0 <= accessor_index < len(accessors):
            continue
        accessor = as_dict(accessors[accessor_index])
        mins = accessor.get("min")
        maxs = accessor.get("max")
        if not isinstance(mins, list) or not isinstance(maxs, list) or len(mins) < 3 or len(maxs) < 3:
            missing_bounds += 1
            continue
        mins_f = [float(mins[0]), float(mins[1]), float(mins[2])]
        maxs_f = [float(maxs[0]), float(maxs[1]), float(maxs[2])]
        if bbox_min is None:
            bbox_min = mins_f
            bbox_max = maxs_f
        else:
            bbox_min = [min(bbox_min[i], mins_f[i]) for i in range(3)]
            bbox_max = [max(bbox_max[i], maxs_f[i]) for i in range(3)]

    extents = None
    if bbox_min is not None and bbox_max is not None:
        extents = [bbox_max[i] - bbox_min[i] for i in range(3)]

    return {
        "mesh_count": len(meshes),
        "primitive_count": primitive_count,
        "face_count": total_faces,
        "vertex_count": total_vertices,
        "index_count": total_indices,
        "lod": classify_lod(total_faces, config.low_faces, config.high_faces),
        "primitive_modes": dict(mode_counter),
        "has_normals": has_normals,
        "has_uvs": has_uvs,
        "bbox_min": bbox_min,
        "bbox_max": bbox_max,
        "bbox_extents": extents,
        "missing_position_bounds": missing_bounds,
    }


def collect_keyword_texts(path: str, relative_path: str, gltf: Optional[Dict[str, Any]]) -> List[str]:
    texts = [path, relative_path, Path(path).name]
    if not gltf:
        return texts
    asset = as_dict(gltf.get("asset"))
    texts.extend(str(value) for value in asset.values() if isinstance(value, str))
    for collection_name in (
        "scenes",
        "nodes",
        "meshes",
        "materials",
        "textures",
        "images",
        "animations",
        "skins",
    ):
        for item in as_list(gltf.get(collection_name)):
            item_dict = as_dict(item)
            name = item_dict.get("name")
            uri = item_dict.get("uri")
            if isinstance(name, str):
                texts.append(name)
            if isinstance(uri, str):
                texts.append(uri)
    texts.extend(iter_string_values(gltf.get("extras")))
    texts.extend(iter_string_values(gltf.get("extensions")))
    return texts


def decide_status(record: Dict[str, Any], config: AuditConfig) -> None:
    reject: List[str] = []
    review: List[str] = []

    if not record.get("exists", False):
        reject.append("missing_file")
    if not record.get("parse_ok", False):
        reject.append("cannot_parse_or_open")
    if record.get("file_size_bytes", 0) <= 0:
        reject.append("empty_file")
    if record.get("invalid_references"):
        reject.append("invalid_gltf_references")
    if record.get("missing_external_images"):
        reject.append("missing_external_images")
    if record.get("unreadable_images"):
        reject.append("unreadable_images")

    if record.get("parse_ok", False):
        if record.get("mesh_count", 0) <= 0:
            reject.append("no_mesh")
        if record.get("primitive_count", 0) <= 0:
            reject.append("no_primitive")
        face_count = int(record.get("face_count", 0))
        if face_count < config.min_faces:
            reject.append("too_few_faces")
        if face_count > config.max_faces:
            reject.append("too_many_faces")
        if record.get("bbox_extents") is not None:
            extents = record["bbox_extents"]
            if max(extents) <= 1e-8:
                reject.append("degenerate_bounds")

        file_size_mb = float(record.get("file_size_mb", 0.0))
        if file_size_mb > config.max_file_mb:
            review.append("file_size_too_large")
        if record.get("lod") == "high":
            review.append("high_poly_model")
        if not record.get("has_normals", False):
            review.append("missing_normals")
        if record.get("has_textures", False) and not record.get("has_uvs", False):
            reject.append("textures_without_uv")
        if not record.get("has_textures", False):
            if config.require_textures:
                reject.append("no_texture")
            else:
                review.append("no_texture")
        if not record.get("has_pbr", False):
            if config.require_pbr:
                reject.append("no_pbr")
            else:
                review.append("no_pbr")
        if record.get("small_textures"):
            review.append("small_texture")
        if record.get("large_textures"):
            review.append("large_texture")
        if record.get("remote_image_count", 0) > 0:
            review.append("remote_texture_uri")
        if record.get("unused_image_count", 0) > 0:
            review.append("unused_images")

    if record.get("ai_suspect", False):
        if config.reject_ai:
            reject.append("ai_asset_suspect")
        else:
            review.append("ai_asset_suspect")
    if record.get("gore_markers"):
        reject.append("gore_keyword_suspect")
    if record.get("violence_markers"):
        if config.reject_violence_keywords:
            reject.append("violence_keyword_suspect")
        else:
            review.append("violence_keyword_suspect")

    record["reject_reasons"] = sorted(set(reject))
    record["review_reasons"] = sorted(set(review))
    if reject:
        record["status"] = "rejected"
    elif review:
        record["status"] = "review"
    else:
        record["status"] = "accepted"


def make_missing_record(path: str, root: Optional[str], config: AuditConfig) -> Dict[str, Any]:
    root_path = Path(root).resolve() if root else None
    path_obj = Path(path)
    record = {
        "path": path,
        "relative_path": safe_relpath(path_obj, root_path),
        "extension": path_obj.suffix.lower(),
        "exists": False,
        "parse_ok": False,
        "file_size_bytes": 0,
        "file_size_mb": 0.0,
        "errors": ["file_not_found"],
        "warnings": [],
        "invalid_references": [],
        "missing_external_images": [],
        "unreadable_images": [],
        "ai_suspect": False,
        "ai_markers": {},
        "content_risk": False,
        "gore_markers": {},
        "violence_markers": {},
    }
    update_ai_assessment(record)
    decide_status(record, config)
    return record


def audit_one(args: Tuple[str, Optional[str], AuditConfig]) -> Dict[str, Any]:
    path, root, config = args
    root_path = Path(root).resolve() if root else None
    path_obj = Path(path)
    record: Dict[str, Any] = {
        "path": path,
        "relative_path": safe_relpath(path_obj, root_path),
        "extension": path_obj.suffix.lower(),
        "exists": os.path.exists(path),
        "parse_ok": False,
        "errors": [],
        "warnings": [],
        "invalid_references": [],
        "missing_external_images": [],
        "unreadable_images": [],
        "small_textures": [],
        "large_textures": [],
        "ai_suspect": False,
        "ai_markers": {},
        "content_risk": False,
        "gore_markers": {},
        "violence_markers": {},
    }

    if not record["exists"]:
        record.update(make_missing_record(path, root, config))
        return record

    record["file_size_bytes"] = os.path.getsize(path)
    record["file_size_mb"] = round(record["file_size_bytes"] / 1024 / 1024, 4)

    if path_obj.suffix.lower() not in SUPPORTED_MODEL_EXTS:
        record["errors"].append("unsupported_extension")
        decide_status(record, config)
        return record

    container: Optional[GltfContainer] = None
    try:
        container = parse_container(path)
        gltf = container.gltf
        record["parse_ok"] = True
        record["warnings"].extend(container.warnings)

        asset = as_dict(gltf.get("asset"))
        record["gltf_version"] = asset.get("version")
        record["gltf_generator"] = asset.get("generator")
        record["has_animation"] = len(as_list(gltf.get("animations"))) > 0
        record["has_skin"] = len(as_list(gltf.get("skins"))) > 0

        invalid_refs, ref_stats = validate_references(gltf)
        record["invalid_references"] = invalid_refs
        record["reference_stats"] = ref_stats

        record.update(analyze_geometry(gltf, config))

        texture_stats, texture_warnings, texture_errors = analyze_textures(path, container, config)
        record.update(texture_stats)
        record["warnings"].extend(texture_warnings)
        record["errors"].extend(texture_errors)

        texts = collect_keyword_texts(path, record["relative_path"], gltf)
        ai_hits = keyword_matches(texts, sorted(AI_KEYWORDS))
        gore_hits = keyword_matches(texts, sorted(GORE_KEYWORDS))
        violence_hits = keyword_matches(texts, sorted(VIOLENCE_KEYWORDS))
        record["ai_markers"] = ai_hits
        record["ai_suspect"] = bool(ai_hits)
        record["gore_markers"] = gore_hits
        record["violence_markers"] = violence_hits
        record["content_risk"] = bool(gore_hits or violence_hits)
    except Exception as exc:
        record["errors"].append(str(exc))

    update_ai_assessment(record)
    decide_status(record, config)
    return record


VIEW_NAMES = ("front", "back", "left", "right", "top", "bottom")


BLENDER_SIX_VIEW_SCRIPT = r'''
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
        raise SystemExit("usage: blender --background --python render.py -- jobs.json results.jsonl")
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
    min_v = Vector((math.inf, math.inf, math.inf))
    max_v = Vector((-math.inf, -math.inf, -math.inf))
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            min_v.x = min(min_v.x, world.x)
            min_v.y = min(min_v.y, world.y)
            min_v.z = min(min_v.z, world.z)
            max_v.x = max(max_v.x, world.x)
            max_v.y = max(max_v.y, world.y)
            max_v.z = max(max_v.z, world.z)
    return min_v, max_v


def look_at(camera, target):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_render(size, engine):
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    try:
        scene.eevee.taa_render_samples = 32
    except Exception:
        pass
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
    except Exception:
        pass
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (1.0, 1.0, 1.0)


def add_lights(center, radius):
    light_data = bpy.data.lights.new("Key_Area", type="AREA")
    light_data.energy = 700
    light_data.size = max(radius * 2.5, 1.0)
    light = bpy.data.objects.new("Key_Area", light_data)
    light.location = center + Vector((radius * 1.5, -radius * 2.0, radius * 2.0))
    bpy.context.collection.objects.link(light)

    fill_data = bpy.data.lights.new("Fill_Sun", type="SUN")
    fill_data.energy = 1.5
    fill = bpy.data.objects.new("Fill_Sun", fill_data)
    fill.rotation_euler = (math.radians(45), 0, math.radians(35))
    bpy.context.collection.objects.link(fill)


def render_job(job):
    path = job["path"]
    render_dir = job["render_dir"]
    prefix = job["prefix"]
    size = int(job["size"])
    engine = job["engine"]
    result = {"path": path, "status": "ok", "images": [], "errors": []}
    try:
        reset_scene()
        import_model(path)
        objects = mesh_objects()
        if not objects:
            raise ValueError("no mesh objects after import")
        min_v, max_v = compute_bounds(objects)
        center = (min_v + max_v) / 2.0
        extents = max_v - min_v
        max_extent = max(extents.x, extents.y, extents.z, 1e-3)
        radius = max_extent * 0.5
        distance = max(max_extent * 2.2, 1.0)

        setup_render(size, engine)
        add_lights(center, radius)
        camera_data = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", camera_data)
        bpy.context.collection.objects.link(camera)
        bpy.context.scene.camera = camera
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = max_extent * 1.35
        camera_data.clip_start = 0.001
        camera_data.clip_end = max(distance * 5.0, 1000.0)

        os.makedirs(render_dir, exist_ok=True)
        for view_name, direction in VIEW_DIRECTIONS.items():
            camera.location = center + direction.normalized() * distance
            look_at(camera, center)
            image_path = os.path.join(render_dir, f"{prefix}_{view_name}.png")
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


def find_blender_executable(config: AuditConfig) -> Optional[str]:
    candidates = [
        config.blender_path,
        os.environ.get("BLENDER_PATH"),
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def render_dir_for_asset(path: str) -> str:
    return str(Path(path).parent / "renders")


def render_prefix_for_asset(path: str) -> str:
    return Path(path).stem


def expected_render_images(path: str) -> List[str]:
    render_dir = render_dir_for_asset(path)
    prefix = render_prefix_for_asset(path)
    return [str(Path(render_dir) / f"{prefix}_{view}.png") for view in VIEW_NAMES]


def mark_existing_render(record: Dict[str, Any]) -> bool:
    images = expected_render_images(str(record.get("path")))
    if images and all(os.path.exists(image_path) for image_path in images):
        record["render_status"] = "existing"
        record["render_dir"] = render_dir_for_asset(str(record.get("path")))
        record["render_images"] = images
        return True
    return False


def render_six_views_for_records(
    records: Sequence[Dict[str, Any]],
    config: AuditConfig,
    only_paths: Optional[set] = None,
) -> Dict[str, Any]:
    selected = []
    for record in records:
        if not record.get("parse_ok"):
            continue
        path = str(record.get("path"))
        if only_paths is not None and path not in only_paths:
            continue
        selected.append(record)

    summary = {"selected": len(selected), "rendered": 0, "existing": 0, "failed": 0, "skipped": 0}
    if not selected:
        return summary

    jobs = []
    for record in selected:
        path = str(record.get("path"))
        record["render_dir"] = render_dir_for_asset(path)
        record["render_images"] = expected_render_images(path)
        if not config.render_overwrite and mark_existing_render(record):
            summary["existing"] += 1
            continue
        jobs.append(
            {
                "path": path,
                "render_dir": render_dir_for_asset(path),
                "prefix": render_prefix_for_asset(path),
                "size": config.render_size,
                "engine": config.render_engine,
            }
        )

    if not jobs:
        return summary

    blender = find_blender_executable(config)
    if not blender:
        for record in selected:
            if record.get("render_status") != "existing":
                record["render_status"] = "skipped_no_blender"
        summary["skipped"] = len(jobs)
        return summary

    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix="_six_view_render.py", delete=False, encoding="utf-8") as script_file:
        script_file.write(BLENDER_SIX_VIEW_SCRIPT)
        script_path = script_file.name
    jobs_path = out_dir / "render_jobs.json"
    results_path = out_dir / "render_results.jsonl"
    with jobs_path.open("w", encoding="utf-8") as writer:
        json.dump(jobs, writer, ensure_ascii=False, indent=2)

    command = [blender, "--background", "--factory-startup", "--python", script_path, "--", str(jobs_path), str(results_path)]
    timeout = max(config.render_timeout_sec, config.render_timeout_sec * max(len(jobs), 1))
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        error_text = (exc.stderr or exc.stdout or str(exc))[-4000:]
        for record in selected:
            if record.get("render_status") != "existing":
                record["render_status"] = "failed"
                record["render_error"] = error_text
        summary["failed"] = len(jobs)
        return summary
    except subprocess.TimeoutExpired as exc:
        error_text = f"Blender render timed out after {timeout}s: {exc}"
        for record in selected:
            if record.get("render_status") != "existing":
                record["render_status"] = "failed"
                record["render_error"] = error_text
        summary["failed"] = len(jobs)
        return summary
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    result_by_path: Dict[str, Dict[str, Any]] = {}
    if results_path.exists():
        with results_path.open("r", encoding="utf-8") as reader:
            for line in reader:
                if line.strip():
                    result = json.loads(line)
                    result_by_path[str(result.get("path"))] = result

    for record in selected:
        if record.get("render_status") == "existing":
            continue
        result = result_by_path.get(str(record.get("path")))
        if not result:
            record["render_status"] = "failed"
            record["render_error"] = "missing Blender render result"
            summary["failed"] += 1
            continue
        record["render_status"] = result.get("status", "failed")
        record["render_images"] = result.get("images", [])
        record["render_dir"] = render_dir_for_asset(str(record.get("path")))
        if result.get("status") == "ok":
            summary["rendered"] += 1
        else:
            record["render_error"] = "; ".join(result.get("errors", []))
            summary["failed"] += 1
    return summary


def select_llm_sample(records: Sequence[Dict[str, Any]], config: AuditConfig) -> List[Dict[str, Any]]:
    candidates = [record for record in records if record.get("parse_ok")]
    candidates.sort(key=lambda item: str(item.get("path", "")))
    if not candidates or config.llm_sample_rate <= 0:
        return []
    sample_count = max(1, int(round(len(candidates) * config.llm_sample_rate)))
    sample_count = min(sample_count, len(candidates))
    if config.llm_max_assets is not None:
        sample_count = min(sample_count, max(config.llm_max_assets, 0))
    rng = random.Random(config.llm_sample_seed)
    sampled = rng.sample(candidates, sample_count)
    sampled.sort(key=lambda item: str(item.get("path", "")))
    for record in sampled:
        record["llm_sampled"] = True
    return sampled


def normalize_ghc_chat_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        raw_url = "http://localhost:8313"
    url = raw_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def image_to_data_url(path: str) -> str:
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_json_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"raw": value}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {"raw": value}


def llm_prompt_for_record(record: Dict[str, Any]) -> str:
    metadata = {
        "relative_path": record.get("relative_path"),
        "static_status": record.get("status"),
        "face_count": record.get("face_count"),
        "lod": record.get("lod"),
        "static_ai_markers": record.get("ai_markers"),
        "static_gore_markers": record.get("gore_markers"),
        "static_violence_markers": record.get("violence_markers"),
        "static_reject_reasons": record.get("reject_reasons"),
        "static_review_reasons": record.get("review_reasons"),
    }
    return (
        "你是3D资产质检专家。下面给你一个GLB资产的前/后/左/右/上/下六视角渲染图，"
        "以及静态文件检测信息。请只基于可见画面和元数据判断资产质量。\n"
        "重点判断：1) 是否疑似AI生成资产；2) 是否符合基础美学/完整性；"
        "3) 是否涉及暴力、血腥、违规内容；4) 是否有碎片、块状、平面片、破损、悬浮、穿模、贴图异常等不合理部件；"
        "5) 其他会影响验收的问题。\n"
        "只返回JSON，不要返回Markdown。字段必须包含：\n"
        "{\n"
        "  \"is_ai_asset\": {\"answer\": \"yes|no|uncertain\", \"confidence\": 0.0, \"reason\": \"...\"},\n"
        "  \"aesthetic_quality\": {\"rating\": \"good|ok|bad\", \"score\": 1, \"reason\": \"...\"},\n"
        "  \"violence_gore\": {\"risk\": \"none|weapon|violence|gore|uncertain\", \"reason\": \"...\"},\n"
        "  \"unreasonable_parts\": {\"has_issue\": true, \"types\": [\"fragment|blocky|flat|broken|floating|penetration|texture|other\"], \"reason\": \"...\"},\n"
        "  \"other_issues\": [\"...\"],\n"
        "  \"acceptance\": {\"decision\": \"pass|review|reject\", \"reason\": \"...\"}\n"
        "}\n"
        f"静态检测信息：{json.dumps(metadata, ensure_ascii=False)}"
    )


def call_ghc_api(record: Dict[str, Any], image_paths: Sequence[str], config: AuditConfig) -> Dict[str, Any]:
    api_url = normalize_ghc_chat_url(config.ghc_api_url or os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL"))
    if not api_url:
        return {"status": "skipped_no_api_url", "error": "set --ghc-api-url or GHC_API_URL/GHC_API_BASE_URL"}

    content: List[Dict[str, Any]] = [{"type": "text", "text": llm_prompt_for_record(record)}]
    for image_path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}})
    payload = {
        "model": config.ghc_api_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": config.ghc_api_temperature,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(config.ghc_api_key_env, "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(api_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.ghc_api_timeout_sec) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")[-2000:]
        return {"status": "failed", "error": f"HTTP {exc.code}: {error_text}"}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}

    try:
        message = response_json["choices"][0]["message"]
        content_text = message.get("content", "")
        parsed = extract_json_object(content_text)
        return {"status": "ok", "response": parsed, "raw_response": response_json}
    except Exception as exc:
        return {"status": "failed", "error": f"cannot parse LLM response: {exc}", "raw_response": response_json}


def run_llm_review(records: Sequence[Dict[str, Any]], sampled_records: Sequence[Dict[str, Any]], config: AuditConfig) -> Dict[str, Any]:
    summary = {"sampled": len(sampled_records), "ok": 0, "failed": 0, "skipped": 0}
    if not sampled_records:
        return summary

    out_path = Path(config.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_path / "llm_review.jsonl"
    csv_path = out_path / "llm_review.csv"
    csv_fields = ["path", "relative_path", "llm_status", "decision", "is_ai_asset", "aesthetic_score", "violence_gore_risk", "unreasonable_parts", "error"]

    def review_one(record: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        image_paths = [image for image in record.get("render_images", []) if os.path.exists(image)]
        if len(image_paths) < 6:
            result = {"status": "skipped_no_render_images", "error": "six rendered view images are required"}
        else:
            result = call_ghc_api(record, image_paths, config)
        return record, result, image_paths

    def apply_llm_result(record: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        acceptance = as_dict(response.get("acceptance"))
        ai_answer = as_dict(response.get("is_ai_asset")).get("answer")
        aesthetic_score = as_dict(response.get("aesthetic_quality")).get("score")
        violence_risk = as_dict(response.get("violence_gore")).get("risk")
        unreasonable = as_dict(response.get("unreasonable_parts"))

        record["llm_status"] = result.get("status")
        record["llm_response"] = response
        record["llm_error"] = result.get("error")
        record["llm_decision"] = acceptance.get("decision")
        record["llm_is_ai_asset"] = ai_answer
        record["llm_aesthetic_score"] = aesthetic_score
        record["llm_violence_gore_risk"] = violence_risk
        record["llm_unreasonable_parts"] = unreasonable
        update_ai_assessment(record)
        return {
            "decision": acceptance.get("decision"),
            "is_ai_asset": ai_answer,
            "aesthetic_score": aesthetic_score,
            "violence_gore_risk": violence_risk,
            "unreasonable_parts": unreasonable,
        }

    def update_summary(result: Dict[str, Any]) -> None:
        status = str(result.get("status", ""))
        if status == "ok":
            summary["ok"] += 1
        elif status.startswith("skipped"):
            summary["skipped"] += 1
        else:
            summary["failed"] += 1

    def print_llm_progress(done: int, total: int) -> None:
        print(
            "LLM review progress: "
            f"{done}/{total} ok={summary['ok']} failed={summary['failed']} skipped={summary['skipped']}",
            flush=True,
        )

    print(
        f"Starting LLM review: {len(sampled_records)} assets, workers={config.llm_workers}, model={config.ghc_api_model}",
        flush=True,
    )
    with jsonl_path.open("w", encoding="utf-8") as jsonl_writer, csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
        csv_writer.writeheader()
        total = len(sampled_records)
        done = 0
        if config.llm_workers <= 1:
            result_iter = (review_one(record) for record in sampled_records)
            for record, result, image_paths in result_iter:
                update_summary(result)
                extracted = apply_llm_result(record, result)
                path = str(record.get("path"))
                jsonl_writer.write(json.dumps({"path": path, "relative_path": record.get("relative_path"), "render_images": image_paths, "result": result}, ensure_ascii=False, sort_keys=True) + "\n")
                csv_writer.writerow({"path": path, "relative_path": record.get("relative_path"), "llm_status": result.get("status"), "decision": extracted["decision"], "is_ai_asset": extracted["is_ai_asset"], "aesthetic_score": extracted["aesthetic_score"], "violence_gore_risk": extracted["violence_gore_risk"], "unreasonable_parts": json.dumps(extracted["unreasonable_parts"], ensure_ascii=False, sort_keys=True), "error": result.get("error", "")})
                done += 1
                print_llm_progress(done, total)
        else:
            with ThreadPoolExecutor(max_workers=config.llm_workers) as executor:
                futures = [executor.submit(review_one, record) for record in sampled_records]
                for future in as_completed(futures):
                    record, result, image_paths = future.result()
                    update_summary(result)
                    extracted = apply_llm_result(record, result)
                    path = str(record.get("path"))
                    jsonl_writer.write(json.dumps({"path": path, "relative_path": record.get("relative_path"), "render_images": image_paths, "result": result}, ensure_ascii=False, sort_keys=True) + "\n")
                    csv_writer.writerow({"path": path, "relative_path": record.get("relative_path"), "llm_status": result.get("status"), "decision": extracted["decision"], "is_ai_asset": extracted["is_ai_asset"], "aesthetic_score": extracted["aesthetic_score"], "violence_gore_risk": extracted["violence_gore_risk"], "unreasonable_parts": json.dumps(extracted["unreasonable_parts"], ensure_ascii=False, sort_keys=True), "error": result.get("error", "")})
                    done += 1
                    print_llm_progress(done, total)
    return summary


def compact_for_csv(record: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for field in CSV_FIELDS:
        value = record.get(field, "")
        if isinstance(value, (list, dict)):
            row[field] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            row[field] = value
    return row


def count_issue_reasons(records: Sequence[Dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        for reason in record.get("reject_reasons", []):
            counter[f"reject:{reason}"] += 1
        for reason in record.get("review_reasons", []):
            counter[f"review:{reason}"] += 1
    return counter


def top_examples(
    records: Sequence[Dict[str, Any]], status: str, max_examples: int
) -> List[Dict[str, Any]]:
    examples = []
    for record in records:
        if record.get("status") != status:
            continue
        examples.append(
            {
                "path": record.get("path"),
                "relative_path": record.get("relative_path"),
                "reject_reasons": record.get("reject_reasons", []),
                "review_reasons": record.get("review_reasons", []),
                "errors": record.get("errors", [])[:3],
            }
        )
        if len(examples) >= max_examples:
            break
    return examples


def top_ai_examples(records: Sequence[Dict[str, Any]], max_examples: int) -> List[Dict[str, Any]]:
    candidates = [
        record
        for record in records
        if int(record.get("ai_score") or 0) > 0 or str(record.get("llm_is_ai_asset") or "").casefold() in {"yes", "uncertain"}
    ]
    candidates.sort(key=lambda record: int(record.get("ai_score") or 0), reverse=True)
    examples = []
    for record in candidates[:max_examples]:
        examples.append(
            {
                "path": record.get("path"),
                "relative_path": record.get("relative_path"),
                "ai_score": record.get("ai_score"),
                "ai_risk": record.get("ai_risk"),
                "ai_evidence": record.get("ai_evidence", [])[:3],
                "llm_is_ai_asset": record.get("llm_is_ai_asset"),
            }
        )
    return examples


def build_summary(
    records: Sequence[Dict[str, Any]],
    config: AuditConfig,
    discovered_count: int,
    missing_count: int,
    elapsed_sec: float,
    render_summary: Optional[Dict[str, Any]] = None,
    llm_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status_counts = Counter(record.get("status", "unknown") for record in records)
    lod_counts = Counter(record.get("lod", "unknown") for record in records if record.get("parse_ok"))
    ext_counts = Counter(record.get("extension", "") for record in records)
    ai_risk_counts = Counter(record.get("ai_risk", "no_evidence") for record in records)
    ai_candidate_count = sum(1 for record in records if int(record.get("ai_score") or 0) > 0)
    static_ai_count = sum(1 for record in records if record.get("ai_suspect"))
    llm_ai_yes_count = sum(1 for record in records if str(record.get("llm_is_ai_asset") or "").casefold() == "yes")
    llm_ai_uncertain_count = sum(1 for record in records if str(record.get("llm_is_ai_asset") or "").casefold() == "uncertain")
    openable_count = sum(1 for record in records if record.get("parse_ok"))
    parse_failed_count = sum(1 for record in records if not record.get("parse_ok"))
    texture_status_counts = Counter(
        record.get("texture_extract_status")
        for record in records
        if record.get("texture_extract_status")
    )
    extracted_texture_count = sum(int(record.get("extracted_texture_count") or 0) for record in records)
    expected_ok = None
    if config.expected_count is not None:
        expected_ok = discovered_count == config.expected_count

    first_level_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        rel_path = record.get("relative_path") or record.get("path") or ""
        first = rel_path.split(os.sep)[0] if rel_path else "root"
        first_level_counts[first][record.get("status", "unknown")] += 1

    dataset_status = "accepted"
    dataset_reasons = []
    if not records:
        dataset_status = "empty"
        dataset_reasons.append("no_model_files_found")
    if expected_ok is False:
        dataset_status = "rejected"
        dataset_reasons.append("expected_count_mismatch")
    if status_counts.get("rejected", 0) > 0:
        dataset_status = "rejected"
        dataset_reasons.append("has_rejected_assets")
    elif status_counts.get("review", 0) > 0 and dataset_status != "rejected":
        dataset_status = "review"
        dataset_reasons.append("has_review_assets")

    return {
        "dataset_status": dataset_status,
        "dataset_reasons": sorted(set(dataset_reasons)),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(elapsed_sec, 3),
        "root": config.root,
        "input_list": config.input_list,
        "out_dir": config.out_dir,
        "expected_count": config.expected_count,
        "expected_count_ok": expected_ok,
        "discovered_count": discovered_count,
        "missing_input_count": missing_count,
        "record_count": len(records),
        "openable_count": openable_count,
        "parse_failed_count": parse_failed_count,
        "status_counts": dict(status_counts),
        "lod_counts": dict(lod_counts),
        "extension_counts": dict(ext_counts),
        "render_summary": render_summary or {},
        "llm_summary": llm_summary or {},
        "ai_summary": {
            "risk_counts": dict(ai_risk_counts),
            "candidate_count": ai_candidate_count,
            "static_keyword_count": static_ai_count,
            "llm_ai_yes_count": llm_ai_yes_count,
            "llm_ai_uncertain_count": llm_ai_uncertain_count,
            "examples": top_ai_examples(records, config.max_examples),
        },
        "texture_extract_summary": {
            "enabled": config.extract_textures,
            "status_counts": dict(texture_status_counts),
            "extracted_texture_count": extracted_texture_count,
        },
        "issue_counts": dict(count_issue_reasons(records).most_common()),
        "first_level_counts": {
            key: dict(value) for key, value in sorted(first_level_counts.items())
        },
        "examples": {
            "rejected": top_examples(records, "rejected", config.max_examples),
            "review": top_examples(records, "review", config.max_examples),
        },
        "rules": {
            "low_faces": config.low_faces,
            "high_faces": config.high_faces,
            "min_faces": config.min_faces,
            "max_faces": config.max_faces,
            "max_file_mb": config.max_file_mb,
            "require_textures": config.require_textures,
            "require_pbr": config.require_pbr,
            "reject_ai": config.reject_ai,
            "reject_violence_keywords": config.reject_violence_keywords,
            "inspect_images": config.inspect_images,
            "pil_available": PIL_AVAILABLE,
            "extract_textures": config.extract_textures,
            "texture_overwrite": config.texture_overwrite,
            "texture_dir_name": config.texture_dir_name,
            "render_six_views": config.render_six_views,
            "render_size": config.render_size,
            "render_engine": config.render_engine,
            "llm_review": config.llm_review,
            "llm_sample_rate": config.llm_sample_rate,
            "llm_sample_seed": config.llm_sample_seed,
            "llm_workers": config.llm_workers,
            "ghc_api_model": config.ghc_api_model,
        },
    }


def pct(part: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part / total * 100:.2f}%"


def render_summary_md(summary: Dict[str, Any]) -> str:
    total = int(summary.get("record_count", 0))
    status_counts = summary.get("status_counts", {})
    lod_counts = summary.get("lod_counts", {})
    issue_counts = summary.get("issue_counts", {})
    render_summary = summary.get("render_summary", {})
    llm_summary = summary.get("llm_summary", {})
    ai_summary = summary.get("ai_summary", {})
    texture_extract_summary = summary.get("texture_extract_summary", {})
    lines = [
        "# GLB 质量验收报告",
        "",
        "## 总览",
        f"- 数据集状态: **{summary.get('dataset_status')}**",
        f"- 扫描目录: `{summary.get('root')}`",
        f"- 输入清单: `{summary.get('input_list')}`",
        f"- 发现模型数: {summary.get('discovered_count')}",
        f"- 记录总数: {total}",
        f"- 可解析/可打开数: {summary.get('openable_count')} ({pct(int(summary.get('openable_count', 0)), total)})",
        f"- 解析失败数: {summary.get('parse_failed_count')} ({pct(int(summary.get('parse_failed_count', 0)), total)})",
        f"- 缺失清单文件数: {summary.get('missing_input_count')}",
        f"- 运行耗时: {summary.get('elapsed_sec')}s",
        "",
    ]
    if summary.get("expected_count") is not None:
        lines.append(
            f"- 期望数量: {summary.get('expected_count')}，数量是否匹配: {summary.get('expected_count_ok')}"
        )
        lines.append("")

    lines.extend(["## 验收状态", ""])
    for key in ("accepted", "review", "rejected", "unknown"):
        count = int(status_counts.get(key, 0))
        if count:
            lines.append(f"- {key}: {count} ({pct(count, total)})")
    if not status_counts:
        lines.append("- 无记录")
    lines.append("")

    lines.extend(["## 精度分布", ""])
    for key in ("low", "mid", "high", "unknown"):
        count = int(lod_counts.get(key, 0))
        if count:
            lines.append(f"- {key}: {count} ({pct(count, int(summary.get('openable_count', 0)))})")
    if not lod_counts:
        lines.append("- 无可解析模型")
    lines.append("")

    lines.extend(["## 主要问题", ""])
    if issue_counts:
        for reason, count in list(issue_counts.items())[:30]:
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- 未发现自动验收问题")
    lines.append("")

    if int(status_counts.get("rejected", 0)) > 0:
        lines.extend(
            [
                "## Rejected 明细",
                "",
                "- 明细文件: `rejected_detail.md` / `rejected_detail.csv` / `rejected_detail.jsonl`",
                "- 每条 rejected 都会给出机器原因、中文说明、具体证据和建议处理动作。",
                "",
            ]
        )

    if ai_summary:
        lines.extend(
            [
                "## AI 资产识别",
                "",
                f"- AI 候选数: {ai_summary.get('candidate_count', 0)}",
                f"- 静态关键词命中数: {ai_summary.get('static_keyword_count', 0)}",
                f"- LLM 判断 AI 数: {ai_summary.get('llm_ai_yes_count', 0)}",
                f"- LLM 不确定数: {ai_summary.get('llm_ai_uncertain_count', 0)}",
                f"- 风险分布: {ai_summary.get('risk_counts', {})}",
                "- 候选明细: `ai_candidates.md` / `ai_candidates.csv` / `ai_candidates.jsonl`",
                "",
            ]
        )
        examples_ai = ai_summary.get("examples", [])[:10]
        if examples_ai:
            lines.append("### AI 候选示例")
            for item in examples_ai:
                evidence = "; ".join(as_list(item.get("ai_evidence"))[:2])
                lines.append(
                    f"- `{item.get('relative_path')}`: score={item.get('ai_score')}, risk={item.get('ai_risk')}, evidence={evidence}"
                )
            lines.append("")

    if render_summary:
        lines.extend(
            [
                "## 六视角渲染",
                "",
                f"- 选择资产数: {render_summary.get('selected', 0)}",
                f"- 新渲染完成: {render_summary.get('rendered', 0)}",
                f"- 已存在跳过: {render_summary.get('existing', 0)}",
                f"- 渲染失败: {render_summary.get('failed', 0)}",
                f"- 跳过: {render_summary.get('skipped', 0)}",
                "- 图片位置: 每个 GLB 当前目录下的 `renders/`",
                "",
            ]
        )

    if texture_extract_summary and texture_extract_summary.get("enabled"):
        lines.extend(
            [
                "## 贴图抽取",
                "",
                f"- 抽取贴图总数: {texture_extract_summary.get('extracted_texture_count', 0)}",
                f"- 状态分布: {texture_extract_summary.get('status_counts', {})}",
                f"- 图片位置: 每个 GLB 当前目录下的 `{summary.get('rules', {}).get('texture_dir_name', 'imgs')}/`",
                "",
            ]
        )

    if llm_summary:
        lines.extend(
            [
                "## LLM 抽检",
                "",
                f"- 抽样数量: {llm_summary.get('sampled', 0)}",
                f"- 调用成功: {llm_summary.get('ok', 0)}",
                f"- 调用失败: {llm_summary.get('failed', 0)}",
                f"- 跳过: {llm_summary.get('skipped', 0)}",
                "- 明细文件: `llm_review.jsonl` / `llm_review.csv`",
                "",
            ]
        )

    lines.extend(["## 抽样示例", ""])
    examples = summary.get("examples", {})
    for group in ("rejected", "review"):
        items = examples.get(group, [])
        lines.append(f"### {group}")
        if not items:
            lines.append("- 无")
            lines.append("")
            continue
        for item in items:
            reasons = item.get("reject_reasons") or item.get("review_reasons") or item.get("errors")
            lines.append(f"- `{item.get('relative_path')}`: {', '.join(reasons)}")
        lines.append("")

    lines.extend(
        [
            "## 使用建议",
            "",
            "- `rejected` 先修复或剔除：解析失败、缺贴图、贴图不可读、GLTF 引用错误、血腥风险词、面数极端异常会直接影响验收。",
            "- `review` 建议人工抽检：疑似 AI、疑似武器/暴力词、高模、无贴图/无 PBR、无 normal、远程贴图 URI 都不一定错误，但需要业务确认。",
            "- 静态检查不能替代最终渲染审核；上线前建议对 `review` 和少量 `accepted` 样本再用 Blender/three.js 批量渲染缩略图复核。",
            "- 如果项目要求必须贴图/PBR，运行时加 `--require-textures --require-pbr`；如果不允许 AI 资产，加 `--reject-ai`。",
        ]
    )
    return "\n".join(lines) + "\n"


def compact_report_row(row: Dict[str, Any], fields: Sequence[str]) -> Dict[str, Any]:
    compacted: Dict[str, Any] = {}
    for field in fields:
        value = row.get(field, "")
        if isinstance(value, (list, dict)):
            compacted[field] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            compacted[field] = value
    return compacted


def reject_reason_evidence(record: Dict[str, Any], reason: str, summary: Dict[str, Any]) -> List[str]:
    rules = as_dict(summary.get("rules"))
    if reason == "too_many_faces":
        return [f"face_count={record.get('face_count')}, max_faces={rules.get('max_faces')}"]
    if reason == "too_few_faces":
        return [f"face_count={record.get('face_count')}, min_faces={rules.get('min_faces')}"]
    if reason == "file_size_too_large":
        return [f"file_size_mb={record.get('file_size_mb')}, max_file_mb={rules.get('max_file_mb')}"]
    if reason == "textures_without_uv":
        uv_errors = as_list(record.get("missing_uv_for_textures"))
        if uv_errors:
            return [str(item) for item in uv_errors[:8]]
        return [str(item) for item in as_list(record.get("errors")) if "TEXCOORD" in str(item)][:8]
    if reason == "invalid_gltf_references":
        return [str(item) for item in as_list(record.get("invalid_references"))[:8]]
    if reason == "missing_external_images":
        return [str(item) for item in as_list(record.get("missing_external_images"))[:8]]
    if reason == "unreadable_images":
        return [str(item) for item in as_list(record.get("unreadable_images"))[:8]]
    if reason == "gore_keyword_suspect":
        return marker_evidence(record.get("gore_markers"), 8)
    if reason == "violence_keyword_suspect":
        return marker_evidence(record.get("violence_markers"), 8)
    if reason == "ai_asset_suspect":
        evidence = marker_evidence(record.get("ai_markers"), 8)
        evidence.extend(as_list(record.get("ai_evidence"))[:4])
        return evidence[:8]
    if reason == "cannot_parse_or_open":
        return [str(item) for item in as_list(record.get("errors"))[:8]]
    if reason in {"no_mesh", "no_primitive", "no_texture", "no_pbr", "degenerate_bounds", "empty_file", "missing_file"}:
        return [
            f"mesh_count={record.get('mesh_count')}",
            f"primitive_count={record.get('primitive_count')}",
            f"image_count={record.get('image_count')}",
            f"texture_count={record.get('texture_count')}",
            f"pbr_material_count={record.get('pbr_material_count')}",
            f"bbox_extents={record.get('bbox_extents')}",
        ]
    return [str(item) for item in as_list(record.get("errors"))[:8]]


def build_rejected_detail_rows(records: Sequence[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        if record.get("status") != "rejected":
            continue
        reason_details: List[str] = []
        evidence: List[str] = []
        suggestions: List[str] = []
        for reason in as_list(record.get("reject_reasons")):
            title, detail, suggestion = REJECT_REASON_DETAILS.get(
                str(reason),
                (str(reason), "该拒收原因尚未登记中文说明。", "人工复核该记录。"),
            )
            reason_details.append(f"{reason}: {title} - {detail}")
            suggestions.append(f"{reason}: {suggestion}")
            for item in reject_reason_evidence(record, str(reason), summary):
                if item and item not in evidence:
                    evidence.append(item)
        if not evidence:
            evidence = [str(item) for item in as_list(record.get("errors"))[:8]]
        row = {field: record.get(field, "") for field in REJECT_DETAIL_FIELDS}
        row["reason_details"] = reason_details
        row["evidence"] = evidence[:16]
        row["suggested_action"] = suggestions
        rows.append(row)
    rows.sort(key=lambda row: str(row.get("relative_path") or row.get("path") or ""))
    return rows


def render_rejected_detail_md(rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# Rejected 资产明细",
        "",
        "每条记录包含拒收原因、可读说明、具体证据和建议处理动作。",
        "",
    ]
    if not rows:
        lines.append("无 rejected 资产。")
        return "\n".join(lines) + "\n"
    for row in rows:
        lines.append(f"## {row.get('relative_path') or row.get('path')}")
        lines.append(f"- 状态: {row.get('status')}，LOD: {row.get('lod')}，faces: {row.get('face_count')}，file_mb: {row.get('file_size_mb')}")
        lines.append(f"- 拒收原因: {', '.join(str(item) for item in as_list(row.get('reject_reasons')))}")
        for field_label, field_name in (
            ("原因说明", "reason_details"),
            ("具体证据", "evidence"),
            ("处理建议", "suggested_action"),
            ("错误", "errors"),
            ("AI 证据", "ai_evidence"),
        ):
            values = [str(item) for item in as_list(row.get(field_name)) if item]
            if values:
                lines.append(f"- {field_label}: {'; '.join(values[:8])}")
        lines.append("")
    return "\n".join(lines)


def build_ai_candidate_rows(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in records:
        ai_score = int(record.get("ai_score") or 0)
        llm_answer = str(record.get("llm_is_ai_asset") or "").casefold()
        if ai_score <= 0 and llm_answer not in {"yes", "uncertain"}:
            continue
        rows.append({field: record.get(field, "") for field in AI_CANDIDATE_FIELDS})
    rows.sort(key=lambda row: int(row.get("ai_score") or 0), reverse=True)
    return rows


def render_ai_candidates_md(rows: Sequence[Dict[str, Any]]) -> str:
    lines = [
        "# AI 候选资产",
        "",
        "评分口径：high >= 75，medium >= 45，low >= 20。静态关键词只是证据之一，不建议单独作为最终拒收依据。",
        "",
    ]
    if not rows:
        lines.append("未发现 AI 候选资产。")
        return "\n".join(lines) + "\n"
    for row in rows:
        lines.append(f"## {row.get('relative_path') or row.get('path')}")
        lines.append(f"- AI 风险: {row.get('ai_risk')}，score: {row.get('ai_score')}，status: {row.get('status')}")
        evidence = [str(item) for item in as_list(row.get("ai_evidence")) if item]
        if evidence:
            lines.append(f"- 证据: {'; '.join(evidence[:8])}")
        action = row.get("ai_review_action")
        if action:
            lines.append(f"- 建议: {action}")
        llm_answer = row.get("llm_is_ai_asset")
        if llm_answer:
            lines.append(f"- LLM: is_ai_asset={llm_answer}, decision={row.get('llm_decision')}")
        lines.append("")
    return "\n".join(lines)


def write_outputs(records: Sequence[Dict[str, Any]], summary: Dict[str, Any], out_dir: str) -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    with (out_path / "assets.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    with (out_path / "assets.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(compact_for_csv(record))

    for status in ("accepted", "review", "rejected"):
        with (out_path / f"{status}.txt").open("w", encoding="utf-8") as handle:
            for record in records:
                if record.get("status") == status:
                    handle.write(str(record.get("path")) + "\n")

    rejected_rows = build_rejected_detail_rows(records, summary)
    with (out_path / "rejected_detail.jsonl").open("w", encoding="utf-8") as handle:
        for row in rejected_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (out_path / "rejected_detail.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REJECT_DETAIL_FIELDS)
        writer.writeheader()
        for row in rejected_rows:
            writer.writerow(compact_report_row(row, REJECT_DETAIL_FIELDS))
    with (out_path / "rejected_detail.md").open("w", encoding="utf-8") as handle:
        handle.write(render_rejected_detail_md(rejected_rows))

    ai_rows = build_ai_candidate_rows(records)
    with (out_path / "ai_candidates.jsonl").open("w", encoding="utf-8") as handle:
        for row in ai_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (out_path / "ai_candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AI_CANDIDATE_FIELDS)
        writer.writeheader()
        for row in ai_rows:
            writer.writerow(compact_report_row(row, AI_CANDIDATE_FIELDS))
    with (out_path / "ai_candidates.md").open("w", encoding="utf-8") as handle:
        handle.write(render_ai_candidates_md(ai_rows))

    with (out_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    with (out_path / "summary.md").open("w", encoding="utf-8") as handle:
        handle.write(render_summary_md(summary))


def parse_args(argv: Optional[Sequence[str]] = None) -> AuditConfig:
    parser = argparse.ArgumentParser(
        description="CPU-only GLB/glTF quality audit: openability, LOD, textures, AI/content risk, acceptance reports."
    )
    parser.add_argument("--root", help="Directory containing GLB/glTF files.")
    parser.add_argument("--input-list", help="Optional newline-separated asset path list.")
    parser.add_argument("--out", default="jiaguyi_eval/glb_quality_report", help="Output report directory.")
    parser.add_argument(
        "--include-exts",
        default=",".join(sorted(DEFAULT_MODEL_EXTS)),
        help="Comma-separated extensions to scan. Supported: .glb,.gltf. Default: .glb",
    )
    parser.add_argument("--expected-count", type=int, help="Expected model count for quantity acceptance.")
    parser.add_argument("--low-faces", type=int, default=50_000, help="Low/mid threshold. Default: 50000")
    parser.add_argument("--high-faces", type=int, default=150_000, help="Mid/high threshold. Default: 150000")
    parser.add_argument("--min-faces", type=int, default=12, help="Reject models below this face count.")
    parser.add_argument("--max-faces", type=int, default=2_000_000, help="Reject models above this face count.")
    parser.add_argument("--max-file-mb", type=float, default=512.0, help="Review models above this file size.")
    parser.add_argument("--require-textures", action="store_true", help="Reject assets without any texture/image.")
    parser.add_argument("--require-pbr", action="store_true", help="Reject assets without PBR material fields.")
    parser.add_argument("--reject-ai", action="store_true", help="Reject assets with AI-generation keyword hits.")
    parser.add_argument(
        "--reject-violence-keywords",
        action="store_true",
        help="Reject general weapon/violence keyword hits. Gore keywords are always rejected.",
    )
    parser.add_argument(
        "--no-image-check",
        action="store_true",
        help="Skip image readability/dimension checks; only references are validated.",
    )
    parser.add_argument("--min-texture-size", type=int, default=64, help="Review textures with any side below this.")
    parser.add_argument("--max-texture-size", type=int, default=8192, help="Review textures with any side above this.")
    parser.add_argument("--workers", type=int, default=min(os.cpu_count() or 1, 8), help="Parallel worker count.")
    parser.add_argument(
        "--list-path-column",
        type=int,
        default=0,
        help="0-based path column when --input-list lines contain metrics. Default: 0",
    )
    parser.add_argument("--sample-limit", type=int, help="Only audit the first N discovered assets.")
    parser.add_argument("--max-examples", type=int, default=30, help="Examples kept in summary files.")
    parser.add_argument("--extract-textures", action="store_true", help="Extract embedded/copy external GLB textures into each asset folder's texture directory.")
    parser.add_argument("--texture-overwrite", action="store_true", help="Overwrite existing files under the texture directory when extracting textures.")
    parser.add_argument("--texture-dir-name", default="imgs", help="Directory name under each asset folder for extracted textures. Default: imgs")
    parser.add_argument("--render-six-views", action="store_true", help="Render front/back/left/right/top/bottom PNGs into each asset folder's renders/ directory.")
    parser.add_argument("--render-overwrite", action="store_true", help="Overwrite existing six-view render images.")
    parser.add_argument("--blender-path", default=os.environ.get("BLENDER_PATH"), help="Blender executable path. Defaults to BLENDER_PATH, blender in PATH, or macOS app path.")
    parser.add_argument("--render-size", type=int, default=768, help="Square render resolution in pixels. Default: 768")
    parser.add_argument("--render-engine", default="BLENDER_EEVEE", help="Blender render engine. Default: BLENDER_EEVEE")
    parser.add_argument("--render-timeout-sec", type=int, default=180, help="Approximate Blender timeout per asset in seconds.")
    parser.add_argument("--llm-review", action="store_true", help="Sample assets, render missing views for the sample, and call ghc-api for visual review.")
    parser.add_argument("--llm-sample-rate", type=float, default=0.10, help="LLM sample rate among parseable assets. Default: 0.10")
    parser.add_argument("--llm-sample-seed", type=int, default=20260603, help="Deterministic LLM sample seed.")
    parser.add_argument("--llm-max-assets", type=int, help="Optional cap for sampled LLM assets.")
    parser.add_argument("--llm-workers", type=int, default=4, help="Concurrent ghc-api requests for LLM review. Default: 4")
    parser.add_argument("--ghc-api-url", default=os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL") or "http://localhost:8313", help="OpenAI-compatible ghc-api base URL or /chat/completions URL. Default: http://localhost:8313")
    parser.add_argument("--ghc-api-key-env", default="GHC_API_KEY", help="Environment variable containing ghc-api key. Default: GHC_API_KEY")
    parser.add_argument("--ghc-api-model", default=os.environ.get("GHC_API_MODEL", "gpt-4o"), help="GHC API vision model name.")
    parser.add_argument("--ghc-api-timeout-sec", type=int, default=120, help="HTTP timeout for one LLM request.")
    parser.add_argument("--ghc-api-temperature", type=float, default=0.0, help="LLM temperature. Default: 0")
    args = parser.parse_args(argv)

    if not args.root and not args.input_list:
        parser.error("At least one of --root or --input-list is required")

    include_exts = normalize_exts(args.include_exts)
    unsupported = [ext for ext in include_exts if ext not in SUPPORTED_MODEL_EXTS]
    if unsupported:
        parser.error(f"Unsupported extensions for CPU static audit: {unsupported}")
    if args.low_faces <= 0 or args.high_faces <= args.low_faces:
        parser.error("--high-faces must be greater than --low-faces")
    if args.workers <= 0:
        parser.error("--workers must be positive")
    if args.list_path_column < 0:
        parser.error("--list-path-column must be >= 0")
    if args.render_size <= 0:
        parser.error("--render-size must be positive")
    if args.render_timeout_sec <= 0:
        parser.error("--render-timeout-sec must be positive")
    if args.llm_sample_rate < 0 or args.llm_sample_rate > 1:
        parser.error("--llm-sample-rate must be between 0 and 1")
    if args.llm_max_assets is not None and args.llm_max_assets < 0:
        parser.error("--llm-max-assets must be >= 0")
    if args.llm_workers <= 0:
        parser.error("--llm-workers must be positive")
    texture_dir_name = args.texture_dir_name.strip()
    if not texture_dir_name or Path(texture_dir_name).is_absolute() or any(part in {"", ".", ".."} for part in Path(texture_dir_name).parts):
        parser.error("--texture-dir-name must be a relative directory name")

    return AuditConfig(
        root=str(Path(args.root).expanduser().resolve()) if args.root else None,
        input_list=str(Path(args.input_list).expanduser().resolve()) if args.input_list else None,
        out_dir=args.out,
        include_exts=include_exts,
        expected_count=args.expected_count,
        low_faces=args.low_faces,
        high_faces=args.high_faces,
        min_faces=args.min_faces,
        max_faces=args.max_faces,
        max_file_mb=args.max_file_mb,
        require_textures=args.require_textures,
        require_pbr=args.require_pbr,
        reject_ai=args.reject_ai,
        reject_violence_keywords=args.reject_violence_keywords,
        inspect_images=not args.no_image_check,
        min_texture_size=args.min_texture_size,
        max_texture_size=args.max_texture_size,
        workers=args.workers,
        list_path_column=args.list_path_column,
        sample_limit=args.sample_limit,
        max_examples=args.max_examples,
        extract_textures=args.extract_textures,
        texture_overwrite=args.texture_overwrite,
        texture_dir_name=texture_dir_name,
        render_six_views=args.render_six_views,
        render_overwrite=args.render_overwrite,
        blender_path=args.blender_path,
        render_size=args.render_size,
        render_engine=args.render_engine,
        render_timeout_sec=args.render_timeout_sec,
        llm_review=args.llm_review,
        llm_sample_rate=args.llm_sample_rate,
        llm_sample_seed=args.llm_sample_seed,
        llm_max_assets=args.llm_max_assets,
        llm_workers=args.llm_workers,
        ghc_api_url=args.ghc_api_url,
        ghc_api_key_env=args.ghc_api_key_env,
        ghc_api_model=args.ghc_api_model,
        ghc_api_timeout_sec=args.ghc_api_timeout_sec,
        ghc_api_temperature=args.ghc_api_temperature,
    )


def run(config: AuditConfig) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    start = time.time()
    files, missing_files = collect_files(config)
    records: List[Dict[str, Any]] = [make_missing_record(path, config.root, config) for path in missing_files]

    if files:
        worker_args = [(path, config.root, config) for path in files]
        if config.workers == 1:
            for item in worker_args:
                records.append(audit_one(item))
        else:
            with ProcessPoolExecutor(max_workers=config.workers) as executor:
                futures = [executor.submit(audit_one, item) for item in worker_args]
                for future in as_completed(futures):
                    records.append(future.result())

    records.sort(key=lambda record: str(record.get("path", "")))

    sampled_records: List[Dict[str, Any]] = []
    render_summary: Dict[str, Any] = {}
    llm_summary: Dict[str, Any] = {}
    if config.llm_review:
        sampled_records = select_llm_sample(records, config)
        sampled_paths = {str(record.get("path")) for record in sampled_records}
    else:
        sampled_paths = set()

    if config.render_six_views or config.llm_review:
        render_scope = None if config.render_six_views else sampled_paths
        render_summary = render_six_views_for_records(records, config, render_scope)

    if config.llm_review:
        llm_summary = run_llm_review(records, sampled_records, config)

    records.sort(key=lambda record: str(record.get("path", "")))
    elapsed = time.time() - start
    summary = build_summary(
        records=records,
        config=config,
        discovered_count=len(files),
        missing_count=len(missing_files),
        elapsed_sec=elapsed,
        render_summary=render_summary,
        llm_summary=llm_summary,
    )
    write_outputs(records, summary, config.out_dir)
    return records, summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    config = parse_args(argv)
    records, summary = run(config)
    print("===== GLB quality audit =====")
    print(f"records: {len(records)}")
    print(f"openable: {summary['openable_count']}")
    print(f"status: {summary['status_counts']}")
    print(f"dataset_status: {summary['dataset_status']}")
    if summary.get("render_summary"):
        print(f"render_summary: {summary['render_summary']}")
    if summary.get("llm_summary"):
        print(f"llm_summary: {summary['llm_summary']}")
    print(f"report_dir: {config.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

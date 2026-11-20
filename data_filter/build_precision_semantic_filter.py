#!/usr/bin/env python3
"""Filter metadata by high-precision 3D generation semantic exclusions."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


INPUTS = (
    ("tex", Path("/Users/mlty/Downloads/metadata_tex_remove.csv")),
    ("github", Path("/Users/mlty/Downloads/metadata_github_remove.csv")),
    ("sket", Path("/Users/mlty/Downloads/metadata_sket_remove.csv")),
    ("cg", Path("/Users/mlty/Downloads/metadata_cg_remove.csv")),
    ("step1x", Path("/Users/mlty/Downloads/metadata_step1x_remove.csv")),
)
PRIMARY_ORDER = (
    "ai_generated",
    "geometry_corruption",
    "proxy_collision_placeholder",
    "fragment_debris",
    "scan_photogrammetry",
    "rough_irregular_surface",
    "rock_stone_subject",
    "meaningless_primitive",
    "animation_frame_export",
    "unfinished_incomplete",
    "lod_lowpoly_decimated",
    "terrain_rock_cave",
    "road_wall_surface",
    "sculpture_bust_scanned_artifact",
    "scene_room_city_asset_pack",
    "billboard_sprite_flat_card",
    "standalone_part",
    "large_base_background_plane",
    "untextured_asset",
)

PATTERNS = {
    "ai_generated": re.compile(
        r"\b(ai[-_ ]generated|generated[-_ ](?:by|with)[-_ ]ai|generative[-_ ]ai|"
        r"text[-_ ]to[-_ ]3d|meshy\.ai|generated[-_ ]with[-_ ]meshy|tripo3d|"
        r"generated[-_ ]with[-_ ]tripo|dreamfusion|shap-e)\b|人工智能生成|ai生成",
        re.IGNORECASE,
    ),
    "geometry_corruption": re.compile(
        r"\b(corrupt(?:ed|ion)[-_ ]mesh|mesh[-_ ]corruption|missing[-_ ]parts?|floating[-_ ]geometry|"
        r"intersecting[-_ ]geometry|severe[-_ ]artifacts?|malformed[-_ ]mesh|broken[-_ ]geometry)\b|"
        r"网格损坏|缺失部件|悬浮几何|严重破面",
        re.IGNORECASE,
    ),
    "proxy_collision_placeholder": re.compile(
        r"\b(collision[-_ ]mesh|collider|proxy[-_ ]mesh|placeholder[-_ ]model|blockout[-_ ]mesh|"
        r"greybox[-_ ]mesh|dummy[-_ ]model)\b|(?:^|[/\\])(?:collision|collider|placeholder|blockout|greybox)(?:[/\\_. -]|$)|"
        r"碰撞体|代理模型|占位模型",
        re.IGNORECASE,
    ),
    "fragment_debris": re.compile(
        r"\b(debris|mesh[-_ ]fragment|object[-_ ]fragment|fragmented[-_ ]asset|shards?|rubble|"
        r"body[-_ ]part|detached[-_ ]part|wreckage)\b|残片|碎片|残骸|断裂部件",
        re.IGNORECASE,
    ),
    "scan_photogrammetry": re.compile(
        r"\b(photogrammetr(?:y|ic)|3d[-_ ]?scan(?:ned)?|reality[-_ ]capture|laser[-_ ]scan|"
        r"metashape[-_ ]scan|agisoft[-_ ]scan)\b|摄影测量|扫描模型|扫描文物",
        re.IGNORECASE,
    ),
    "rough_irregular_surface": re.compile(
        r"\b((?:rough|uneven|irregular|jagged|bumpy|coarse)[-_ ](?:surface|geometry|mesh)|"
        r"rough[-_ ](?:and[-_ ])?irregular[-_ ](?:surface|geometry|mesh)|"
        r"irregular[-_ ](?:and[-_ ])?(?:jagged|lumpy|uneven)[-_ ](?:surface|geometry|mesh)|"
        r"(?:jagged|lumpy|uneven)[-_ ]irregular[-_ ](?:surface|geometry|mesh)|"
        r"severely[-_ ]uneven[-_ ](?:surface|geometry)|rough[-_ ]sculpture|"
        r"coarse[-_ ]malformed[-_ ](?:surface|geometry)|deformed[-_ ]rough[-_ ]mesh)\b|"
        r"粗糙不规则表面|粗糙畸形几何|严重凹凸不平",
        re.IGNORECASE,
    ),
    "rock_stone_subject": re.compile(
        r"\b((?:a|an|single|large|small|cluster[-_ ]of|pile[-_ ]of)[-_ ]"
        r"(?:rough[-_ ])?(?:rock|rocks|stone|stones|boulder|boulders)(?![-_ ]like[-_ ](?:creature|monster|animal))|"
        r"(?:rock|stone|boulder)[-_ ](?:formation|pile|cluster|outcrop|specimen)|"
        r"(?:pile|cluster)[-_ ]of[-_ ](?:rocks|stones|boulders))\b|"
        r"石头主体|岩石主体|石堆|岩石标本",
        re.IGNORECASE,
    ),
    "meaningless_primitive": re.compile(
        r"\b(test[-_ ](?:cube|sphere|cylinder|torus)|primitive[-_ ](?:cube|sphere|cylinder|torus)|"
        r"dummy[-_ ]mesh|basic[-_ ]geometric[-_ ]shape)\b|测试立方体|基础几何体",
        re.IGNORECASE,
    ),
    "unfinished_incomplete": re.compile(
        r"\b(unfinished[-_ ]model|incomplete[-_ ]model|work[-_ ]in[-_ ]progress[-_ ]model|"
        r"wip[-_ ]model|missing[-_ ]geometry)\b|未完成模型|不完整模型",
        re.IGNORECASE,
    ),
    "lod_lowpoly_decimated": re.compile(
        r"(?:^|[/_. -])lod[1-9][0-9]*(?:[/_. -]|$)|\b(low[-_ ]poly|lowpoly|"
        r"decimat(?:ed|ion)|simplified[-_ ]mesh)\b|低模",
        re.IGNORECASE,
    ),
    "terrain_rock_cave": re.compile(
        r"\b(terrain[-_ ](?:asset|model|tile|mesh)|rock[-_ ](?:asset|model|formation)|"
        r"single[-_ ](?:rock|boulder)[- _]?(?:asset|model)?|boulder[-_ ](?:asset|model)|"
        r"cave[-_ ](?:asset|model|interior)|cliff[-_ ](?:asset|model)|gravel[-_ ]pile)\b|"
        r"地形模型|岩石模型|洞穴模型|悬崖模型",
        re.IGNORECASE,
    ),
    "road_wall_surface": re.compile(
        r"\b(road[-_ ](?:surface|segment|tile|mesh|asset)|wall[-_ ](?:segment|tile|mesh|asset)|"
        r"floor[-_ ](?:surface|tile|plane|mesh)|sidewalk[-_ ](?:segment|tile|mesh))\b|"
        r"道路模型|墙面模型|地板平面",
        re.IGNORECASE,
    ),
    "sculpture_bust_scanned_artifact": re.compile(
        r"\b(sculpture|statue|bust|scanned[-_ ]artifact|museum[-_ ]artifact)\b|雕塑|雕像|半身像|扫描文物",
        re.IGNORECASE,
    ),
    "scene_room_city_asset_pack": re.compile(
        r"\b(complete[-_ ]scene|environment[-_ ]scene|full[-_ ]scene|room[-_ ]scene|interior[-_ ]scene|"
        r"city[-_ ]scene|street[-_ ]scene|village[-_ ]scene|asset[-_ ]pack|model[-_ ]pack|"
        r"diorama|level[-_ ]environment)\b|完整场景|房间场景|城市场景|组合资产包",
        re.IGNORECASE,
    ),
    "billboard_sprite_flat_card": re.compile(
        r"\b(billboard[-_ ](?:sprite|plane|card)|sprite[-_ ](?:plane|card|mesh)|"
        r"flat[-_ ]card|impostor[-_ ](?:plane|card|mesh))\b|广告牌平面|精灵平面|平面卡片",
        re.IGNORECASE,
    ),
    "standalone_part": re.compile(
        r"\b(head[-_ ]only|hand[-_ ]only|arm[-_ ]only|leg[-_ ]only|torso[-_ ]only|"
        r"standalone[-_ ](?:head|hand|clothing|garment|weapon)|single[-_ ]body[-_ ]part|"
        r"clothing[-_ ]only|garment[-_ ]only|weapon[-_ ]part)\b|单独头部|单独手部|身体部件|服装部件|武器零件",
        re.IGNORECASE,
    ),
    "large_base_background_plane": re.compile(
        r"\b(large[-_ ](?:display[-_ ])?base|oversized[-_ ]base|huge[-_ ]base|"
        r"background[-_ ]plane|ground[-_ ]plane|large[-_ ]floor[-_ ]plane)\b|巨大底座|背景平面",
        re.IGNORECASE,
    ),
    "untextured_asset": re.compile(
        r"\b(untextured[-_ ](?:asset|model|mesh)|no[-_ ]textures?|without[-_ ]textures?|"
        r"missing[-_ ]textures?)\b|无纹理模型|缺失纹理",
        re.IGNORECASE,
    ),
}

ACTION_DIR = re.compile(
    r"[/\\](idle|walk|run|attack|dead|death|skill|jump|damage|animation|animations)[^/\\]*[/\\]",
    re.IGNORECASE,
)
NUMBERED_FRAME = re.compile(r"(?:\(\d+\)|[_ .-]\d{3,6})\.(?:obj|fbx)$", re.IGNORECASE)
FRAME_NUMBER = re.compile(r"(?:\(\d+\)|[_ .-]\d{3,6})(?=\.(?:obj|fbx)$)", re.IGNORECASE)
OUTPUT_FIELDS = (
    "dataset", "source_row", "sha256", "local_path", "file_identifier",
    "primary_reason", "all_reasons", "original_decision", "aesthetic_score",
    "face_count", "max_texture", "voxel_blocks", "text_evidence",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-dir", type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument(
        "--out-dir", type=Path,
        default=Path(__file__).with_name("precision_semantic_filter"),
    )
    return parser.parse_args()


def iter_analysis_rows(path: Path) -> Iterator[dict[str, str]]:
    for filename in ("reject_candidates.csv", "review_candidates.csv", "keep_candidates.csv"):
        with (path / filename).open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield from csv.DictReader(handle)


def inner_path(local_path: str) -> str:
    position = local_path.lower().find(".zip/")
    return local_path[position + 5:] if position >= 0 else local_path


def animation_group(local_path: str) -> str:
    return FRAME_NUMBER.sub("#", inner_path(local_path).lower())


def classify(text: str) -> set[str]:
    return {reason for reason, pattern in PATTERNS.items() if pattern.search(text)}


def percentage(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total else "0.00%"


def number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def threshold_failures(row: dict[str, str]) -> list[str]:
    failures = []
    blocks = number(row.get("voxel_blocks", ""))
    if blocks is None:
        failures.append("voxel_missing")
    elif blocks < 2_000:
        failures.append("voxel_below_2000")
    elif blocks > 25_000:
        failures.append("voxel_above_25000")
    score = number(row.get("aesthetic_score", ""))
    if score is not None and score < 5.0:
        failures.append("aesthetic_below_5")
    faces = number(row.get("face_count", ""))
    if faces is not None and faces < 5_000:
        failures.append("face_count_below_5000")
    elif faces is not None and faces > 1_000_000:
        failures.append("face_count_above_1000000")
    return failures


def build_report(summary: dict[str, object]) -> str:
    lines = [
        "# 高精度 3D Generation 语义过滤", "",
        "## 汇总", "",
        f"- 输入总数：{summary['total']:,}",
        f"- 过滤数量：{summary['excluded']:,}（{percentage(summary['excluded'], summary['total'])}）",
        f"- 过滤后数量：{summary['remaining']:,}",
        f"- 继续应用数值门槛后删除：{summary['threshold_excluded']:,}；最终保留：{summary['final_remaining']:,}。",
        "- 数值门槛：体素 2,000-25,000；有效审美分 >=5.0；已有面数字段时 5,000-1,000,000。",
        "- 缺失面数或审美分不删除；缺失体素删除。本结果不包含 SHA 去重。",
        "", "## 各数据源", "",
        "| 数据源 | 原始 | 语义过滤 | 阈值过滤 | 总过滤 | 最终保留 |", "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dataset in ("tex", "github", "sket", "cg", "step1x"):
        total = summary["dataset_totals"][dataset]
        excluded = summary["dataset_excluded"].get(dataset, 0)
        threshold = summary["dataset_threshold_excluded"].get(dataset, 0)
        lines.append(f"| {dataset} | {total:,} | {excluded:,} | {threshold:,} | {excluded + threshold:,} | {total - excluded - threshold:,} |")

    lines.extend(["", "## 互斥主原因", "", "| 原因 | 数量 | 占过滤数据 |", "| --- | ---: | ---: |"])
    for reason in PRIMARY_ORDER:
        count = summary["primary_reasons"].get(reason, 0)
        lines.append(f"| `{reason}` | {count:,} | {percentage(count, summary['excluded'])} |")

    lines.extend(["", "## 数据源 × 主原因", "", "| 数据源 | " + " | ".join(f"`{reason}`" for reason in PRIMARY_ORDER) + " |"])
    lines.append("| --- | " + " | ".join("---:" for _ in PRIMARY_ORDER) + " |")
    for dataset in ("tex", "github", "sket", "cg", "step1x"):
        counts = summary["dataset_primary"].get(dataset, {})
        lines.append(f"| {dataset} | " + " | ".join(f"{counts.get(reason, 0):,}" for reason in PRIMARY_ORDER) + " |")

    lines.extend([
        "", "## 口径", "",
        "- `low-poly` caption 按用户策略过滤；它表示风格/复杂度不匹配，不一定是制作损坏。",
        "- 普通 `test`、`demo`、`example` 不单独过滤；只过滤 `test cube` 等明确无意义基础体。",
        "- `road`、`wall`、`rock` 使用主体短语，避免把石材、墙边配件等正常资产全部误删。",
        "- 动画逐帧要求同一编号模式至少出现两条，整组过滤。",
        "- 无纹理仅适用于纹理/PBR 或高质量外观生成训练；纯几何训练应恢复该类。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = list(iter_analysis_rows(args.analysis_dir))

    animation_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        path = inner_path(row["local_path"])
        if ACTION_DIR.search(path) and NUMBERED_FRAME.search(path):
            animation_groups[animation_group(row["local_path"])].append((row["dataset"], row["source_row"]))
    animation_keys = {
        key for group_rows in animation_groups.values() if len(group_rows) >= 2 for key in group_rows
    }

    excluded_keys: dict[str, set[int]] = defaultdict(set)
    dataset_totals: Counter[str] = Counter()
    dataset_excluded: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    membership_counts: Counter[str] = Counter()
    dataset_primary: dict[str, Counter[str]] = defaultdict(Counter)

    candidates_path = args.out_dir / "exclusion_candidates.csv"
    with candidates_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            dataset = row["dataset"]
            dataset_totals[dataset] += 1
            path_text = inner_path(row["local_path"])
            text = f"{path_text} {row['file_identifier']} {row['text_evidence']}"
            reasons = classify(text)
            original_reasons = set(row["reasons"].split(";"))
            if "lod_or_optimized" in original_reasons:
                reasons.add("lod_lowpoly_decimated")
            if dataset == "tex" and "explicit_ai_generated" in original_reasons:
                reasons.add("ai_generated")
            if dataset == "tex" and "scan_photogrammetry" in original_reasons:
                reasons.add("scan_photogrammetry")
            if (dataset, row["source_row"]) in animation_keys:
                reasons.add("animation_frame_export")
            if not reasons:
                continue
            primary = next(reason for reason in PRIMARY_ORDER if reason in reasons)
            excluded_keys[dataset].add(int(row["source_row"]))
            dataset_excluded[dataset] += 1
            primary_counts[primary] += 1
            membership_counts.update(reasons)
            dataset_primary[dataset][primary] += 1
            writer.writerow({
                "dataset": dataset,
                "source_row": row["source_row"],
                "sha256": row["sha256"],
                "local_path": row["local_path"],
                "file_identifier": row["file_identifier"],
                "primary_reason": primary,
                "all_reasons": ";".join(reason for reason in PRIMARY_ORDER if reason in reasons),
                "original_decision": row["decision"],
                "aesthetic_score": row["aesthetic_score"],
                "face_count": row["face_count"],
                "max_texture": row["max_texture"],
                "voxel_blocks": row["voxel_blocks"],
                "text_evidence": row["text_evidence"],
            })

    filtered_dir = args.out_dir / "filtered"
    filtered_dir.mkdir(exist_ok=True)
    filtered_files = {}
    for dataset, input_path in INPUTS:
        output_path = filtered_dir / f"{input_path.stem}_precision_semantic_filtered.csv"
        with input_path.open(encoding="utf-8-sig", errors="replace", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            with output_path.open("w", encoding="utf-8-sig", newline="") as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames or [])
                writer.writeheader()
                for row_number, row in enumerate(reader, start=1):
                    if row_number not in excluded_keys[dataset]:
                        writer.writerow(row)
        filtered_files[dataset] = str(output_path)

    threshold_counts: Counter[str] = Counter()
    dataset_threshold_counts: Counter[str] = Counter()
    final_excluded_keys: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        dataset = row["dataset"]
        row_number = int(row["source_row"])
        if row_number in excluded_keys[dataset]:
            continue
        failures = threshold_failures(row)
        if not failures:
            continue
        final_excluded_keys[dataset].add(row_number)
        dataset_threshold_counts[dataset] += 1
        threshold_counts.update(failures)

    combined_files = {}
    for dataset, input_path in INPUTS:
        output_path = filtered_dir / f"{input_path.stem}_precision_semantic_numeric_filtered.csv"
        with input_path.open(encoding="utf-8-sig", errors="replace", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            with output_path.open("w", encoding="utf-8-sig", newline="") as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames or [])
                writer.writeheader()
                for row_number, row in enumerate(reader, start=1):
                    if row_number not in excluded_keys[dataset] and row_number not in final_excluded_keys[dataset]:
                        writer.writerow(row)
        combined_files[dataset] = str(output_path)

    total = sum(dataset_totals.values())
    excluded = sum(dataset_excluded.values())
    threshold_excluded = sum(dataset_threshold_counts.values())
    summary = {
        "total": total,
        "excluded": excluded,
        "remaining": total - excluded,
        "threshold_excluded": threshold_excluded,
        "final_remaining": total - excluded - threshold_excluded,
        "dataset_totals": dict(dataset_totals),
        "dataset_excluded": dict(dataset_excluded),
        "dataset_threshold_excluded": dict(dataset_threshold_counts),
        "threshold_failure_memberships": dict(threshold_counts.most_common()),
        "primary_reasons": dict(primary_counts),
        "reason_memberships": dict(membership_counts.most_common()),
        "dataset_primary": {dataset: dict(counts) for dataset, counts in dataset_primary.items()},
        "animation_groups": sum(len(group_rows) >= 2 for group_rows in animation_groups.values()),
        "animation_rows": len(animation_keys),
        "filtered_files": filtered_files,
        "combined_filtered_files": combined_files,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "summary.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
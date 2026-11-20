#!/usr/bin/env python3
"""Find additional training exclusions from duplication, paths, and source concentration."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator


DEFAULT_INPUTS = (
    ("tex", Path("/Users/mlty/Downloads/metadata_tex_remove.csv")),
    ("github", Path("/Users/mlty/Downloads/metadata_github_remove.csv")),
    ("sket", Path("/Users/mlty/Downloads/metadata_sket_remove.csv")),
    ("cg", Path("/Users/mlty/Downloads/metadata_cg_remove.csv")),
    ("step1x", Path("/Users/mlty/Downloads/metadata_step1x_remove.csv")),
)
OUTPUT_FIELDS = (
    "dataset", "source_row", "sha256", "local_path", "file_identifier",
    "action", "reasons", "canonical_dataset", "canonical_source_row", "canonical_local_path",
)

REPO_PATTERN = re.compile(r"^raw/github/repos/([^/]+/[^/]+\.zip)(?:/|$)", re.IGNORECASE)
ACTION_DIR_PATTERN = re.compile(
    r"[/\\](idle|walk|run|attack|dead|death|skill|jump|damage|animation|animations)[^/\\]*[/\\]",
    re.IGNORECASE,
)
NUMBERED_FRAME_PATTERN = re.compile(r"(?:\(\d+\)|[_ .-]\d{3,6})\.(?:obj|fbx)$", re.IGNORECASE)
FRAME_NUMBER_PATTERN = re.compile(r"(?:\(\d+\)|[_ .-]\d{3,6})(?=\.(?:obj|fbx)$)", re.IGNORECASE)
PATH_PATTERNS = {
    "explicit_low_quality": re.compile(
        r"(?:^|[/ _.-])(low[ _-]?quality|poor[ _-]?quality|bad[ _-]?models?)(?:[/ _.-]|$)",
        re.IGNORECASE,
    ),
    "collision_or_proxy": re.compile(
        r"(?:^|[/ _.-])(collider|collision|proxy|placeholder|dummy|blockout|greybox)(?:[/ _.-]|$)",
        re.IGNORECASE,
    ),
    "explicit_no_texture": re.compile(
        r"(?:^|[/ _.-])(no[ _-]?textures?|untextured|without[ _-]?textures?)(?:[/ _.-]|$)",
        re.IGNORECASE,
    ),
    "temporary_or_backup": re.compile(
        r"(?:^|[/\\])(temp|tmp|backup|backups|deprecated|old|wip|unfinished|junk)(?:[/\\]|$)",
        re.IGNORECASE,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).with_name("training_exclusion_analysis"),
    )
    parser.add_argument(
        "--repository-cap",
        type=int,
        default=500,
        help="Report repositories exceeding this row count; does not automatically exclude them",
    )
    return parser.parse_args()


def iter_csv(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=1):
            yield row_number, row


def repository_name(local_path: str) -> str:
    match = REPO_PATTERN.match(local_path)
    return match.group(1) if match else ""


def path_inside_archive(local_path: str) -> str:
    lower = local_path.lower()
    marker_index = lower.find(".zip/")
    return local_path[marker_index + 5:] if marker_index >= 0 else local_path


def is_animation_frame(local_path: str) -> bool:
    return bool(ACTION_DIR_PATTERN.search(local_path) and NUMBERED_FRAME_PATTERN.search(local_path))


def animation_group(local_path: str) -> str:
    return FRAME_NUMBER_PATTERN.sub("#", local_path.lower())


def canonical_rank(dataset: str, row: dict[str, str]) -> tuple[int, int, int, int]:
    status = (row.get("64_15_occ4_block_status") or row.get("64_15_occ8_block_status") or "").strip()
    source_priority = {"github": 5, "tex": 4, "sket": 3, "cg": 2, "step1x": 1}
    return (
        int(status == "success"),
        int(bool((row.get("captions") or "").strip())),
        int(bool((row.get("aesthetic_score") or "").strip())),
        source_priority[dataset],
    )


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_report(summary: dict[str, object]) -> str:
    totals = summary["totals"]
    assert isinstance(totals, dict)
    lines = [
        "# 训练集新增撤出维度分析", "",
        "## 结论", "",
        f"- 精确 SHA256 重复冗余：{totals['exact_duplicate_extra_rows']:,} 条。合并训练集时可安全只保留一份；canonical 优先选择处理成功且元数据完整的副本。",
        f"- 动作序列逐帧导出：识别 {totals['animation_frame_rows']:,} 条，形成 {totals['animation_frame_groups']:,} 个多帧组；"
        f"每组仅留一个代表可减少 {totals['animation_frame_extras']:,} 条。",
        f"- 明确低价值路径：{totals['direct_path_exclusions']:,} 条，包括自报低质量和碰撞体/代理模型。",
        f"- 明确无纹理路径：{totals['no_texture_candidates']:,} 条；仅对纹理或材质训练建议撤出。",
        f"- 临时、备份、旧版或 WIP 路径：{totals['temporary_review']:,} 条；需结合重复关系或渲染确认，不应仅凭名称删除。",
        f"- D0+D1+D2 跨维度去重后的保守撤出候选：{totals['conservative_unique_exclusions']:,} 条。",
        "", "## 可执行层级", "",
        "| 层级 | 含义 | 建议 |", "| --- | --- | --- |",
        "| D0 | 精确 SHA 重复 | 合并训练集时保留 canonical，撤出其余副本 |",
        "| D1 | 自报低质量、碰撞体、代理或占位模型 | 人工快速核验后撤出 |",
        "| D2 | 动画逐帧网格 | 每组保留代表或整组撤出，防止姿态近重复主导训练 |",
        "| D3 | 明确无纹理 | 纹理/PBR 训练撤出；纯几何训练可保留 |",
        "| R | 临时、备份、旧版、WIP | 仅复核，不自动撤出 |",
        "| BALANCE | 单仓库过度集中 | 通过仓库采样上限降权，不视为质量问题 |",
        "", "## 精确重复来源关系", "",
        "| canonical -> duplicate | 数量 |", "| --- | ---: |",
    ]
    for relation, count in summary["duplicate_relations"].items():
        lines.append(f"| `{relation}` | {count:,} |")

    lines.extend(["", "## 与原质量分层交叉", "", "| 原分层 | 新保守撤出候选 |", "| --- | ---: |"])
    for tier, count in summary["previous_tier_cross"].items():
        lines.append(f"| {tier} | {count:,} |")
    lines.extend([
        "",
        f"其中 {summary['net_outside_previous_p0_p1']:,} 条不在原 P0/P1。多数原本属于 Keep，"
        "原因是精确重复和动画帧冗余不属于单体视觉质量问题。",
    ])

    lines.extend(["", "## 路径信号", "", "| 信号 | 数量 |", "| --- | ---: |"])
    for reason, count in summary["path_reason_counts"].items():
        lines.append(f"| `{reason}` | {count:,} |")

    lines.extend(["", "## 高集中仓库", "", "| 仓库 | 资产数 | 数据集占比 |", "| --- | ---: | ---: |"])
    github_total = summary["dataset_rows"]["github"]
    for repository, count in summary["concentrated_repositories"].items():
        lines.append(f"| `{repository}` | {count:,} | {count / github_total:.2%} |")

    lines.extend(["", "## 元数据可用性", "", "| 项目 | 数量 |", "| --- | ---: |"])
    for key, count in summary["metadata_counts"].items():
        lines.append(f"| `{key}` | {count:,} |")

    lines.extend([
        "", "## 限制", "",
        "- SHA256 去重只识别字节完全相同的文件，无法识别重新导出、改纹理或改格式后的近重复。",
        "- 动画逐帧规则要求动作目录和编号文件同时出现，精度较高但可能漏掉命名不规范的序列。",
        "- 仓库规模大不代表质量差；该维度只用于控制来源偏置，不能直接删除整个仓库。",
        "- caption 在当前 GitHub 表中没有精确重复，无法作为新增去重依据。",
        "- 真正的几何破损、法线、纹理和主体完整性仍需渲染或直接解析模型。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    canonical_by_sha: dict[str, tuple[tuple[int, int, int, int], str, int, str]] = {}
    duplicate_rows: list[dict[str, str]] = []
    path_rows: list[dict[str, str]] = []
    animation_rows: list[dict[str, str]] = []
    animation_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    repository_counts: Counter[str] = Counter()
    path_reason_counts: Counter[str] = Counter()
    duplicate_relations: Counter[str] = Counter()
    metadata_counts: Counter[str] = Counter()
    dataset_rows: Counter[str] = Counter()
    caption_counts: Counter[str] = Counter()

    for dataset, path in DEFAULT_INPUTS:
        for row_number, row in iter_csv(path):
            sha256 = row.get("sha256", "").strip().lower()
            if not sha256:
                continue
            candidate = (canonical_rank(dataset, row), dataset, row_number, row.get("local_path", "").strip())
            current = canonical_by_sha.get(sha256)
            if current is None or candidate[0] > current[0]:
                canonical_by_sha[sha256] = candidate

    for dataset, path in DEFAULT_INPUTS:
        for row_number, row in iter_csv(path):
            dataset_rows[dataset] += 1
            sha256 = row.get("sha256", "").strip().lower()
            local_path = row.get("local_path", "").strip()
            file_identifier = row.get("file_identifier", "").strip()
            if sha256:
                canonical = canonical_by_sha.get(sha256)
                if canonical is not None and (dataset, row_number) != (canonical[1], canonical[2]):
                    duplicate_relations[f"{canonical[1]} -> {dataset}"] += 1
                    duplicate_rows.append({
                        "dataset": dataset,
                        "source_row": str(row_number),
                        "sha256": sha256,
                        "local_path": local_path,
                        "file_identifier": file_identifier,
                        "action": "exclude_duplicate",
                        "reasons": "exact_sha256_duplicate",
                        "canonical_dataset": canonical[1],
                        "canonical_source_row": str(canonical[2]),
                        "canonical_local_path": canonical[3],
                    })

            caption = (row.get("captions") or "").strip()
            if dataset == "github":
                metadata_counts["github_missing_caption"] += not caption
                metadata_counts["github_missing_aesthetic_score"] += not (row.get("aesthetic_score") or "").strip()
                if caption:
                    caption_counts[caption] += 1
                repository = repository_name(local_path)
                if repository:
                    repository_counts[repository.lower()] += 1

                inner_path = path_inside_archive(local_path)
                reasons = [reason for reason, pattern in PATH_PATTERNS.items() if pattern.search(inner_path)]
                if is_animation_frame(inner_path):
                    reasons.append("animation_frame_export")
                    candidate = {
                        "dataset": dataset,
                        "source_row": str(row_number),
                        "sha256": sha256,
                        "local_path": local_path,
                        "file_identifier": file_identifier,
                        "action": "deduplicate_animation_sequence",
                        "reasons": "animation_frame_export",
                        "canonical_dataset": "",
                        "canonical_source_row": "",
                        "canonical_local_path": "",
                    }
                    animation_rows.append(candidate)
                    animation_groups[animation_group(local_path)].append(candidate)

                path_reason_counts.update(reasons)
                direct = {"explicit_low_quality", "collision_or_proxy"}.intersection(reasons)
                if direct or "explicit_no_texture" in reasons or "temporary_or_backup" in reasons:
                    if direct:
                        action = "exclude_after_quick_review"
                    elif "explicit_no_texture" in reasons:
                        action = "exclude_for_texture_training"
                    else:
                        action = "review_only"
                    path_rows.append({
                        "dataset": dataset,
                        "source_row": str(row_number),
                        "sha256": sha256,
                        "local_path": local_path,
                        "file_identifier": file_identifier,
                        "action": action,
                        "reasons": ";".join(reasons),
                        "canonical_dataset": "",
                        "canonical_source_row": "",
                        "canonical_local_path": "",
                    })

    animation_group_rows = []
    animation_exclusion_rows: list[dict[str, str]] = []
    for group, rows in animation_groups.items():
        if len(rows) < 2:
            continue
        representative = rows[0]
        for row in rows[1:]:
            row["action"] = "exclude_animation_frame_duplicate"
            row["canonical_dataset"] = representative["dataset"]
            row["canonical_source_row"] = representative["source_row"]
            row["canonical_local_path"] = representative["local_path"]
            animation_exclusion_rows.append(row)
        animation_group_rows.append({
            "group": group,
            "row_count": len(rows),
            "recommended_exclusions_if_keep_one": len(rows) - 1,
            "representative_path": representative["local_path"],
        })
    animation_group_rows.sort(key=lambda row: (-int(row["row_count"]), str(row["group"])))

    concentrated = {
        repository: count
        for repository, count in repository_counts.most_common()
        if count > args.repository_cap
    }
    direct_path_count = sum(
        row["action"] == "exclude_after_quick_review" for row in path_rows
    )
    no_texture_count = sum(
        row["action"] == "exclude_for_texture_training" for row in path_rows
    )
    temporary_count = sum(row["action"] == "review_only" for row in path_rows)
    duplicate_keys = {(row["dataset"], row["source_row"]) for row in duplicate_rows}
    direct_rows = [row for row in path_rows if row["action"] == "exclude_after_quick_review"]
    direct_keys = {(row["dataset"], row["source_row"]) for row in direct_rows}
    conservative_rows = list(duplicate_rows)
    conservative_rows.extend(row for row in direct_rows if (row["dataset"], row["source_row"]) not in duplicate_keys)
    covered_keys = duplicate_keys | direct_keys
    conservative_rows.extend(
        row for row in animation_exclusion_rows
        if (row["dataset"], row["source_row"]) not in covered_keys
    )

    previous_tiers: dict[tuple[str, str], str] = {}
    detail_dir = Path(__file__).with_name("removed_metadata_analysis") / "detail"
    for tier in ("p0", "p1", "reprocess", "p2", "p3"):
        tier_path = detail_dir / f"{tier}_candidates.csv"
        if not tier_path.is_file():
            continue
        with tier_path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                previous_tiers[(row["dataset"], row["source_row"])] = tier.upper()
    previous_tier_cross = Counter(
        previous_tiers.get((row["dataset"], row["source_row"]), "KEEP")
        for row in conservative_rows
    )
    net_outside_previous_p0_p1 = (
        len(conservative_rows) - previous_tier_cross["P0"] - previous_tier_cross["P1"]
    )

    summary = {
        "dataset_rows": dict(dataset_rows),
        "totals": {
            "all_rows": sum(dataset_rows.values()),
            "unique_sha256": len(canonical_by_sha),
            "exact_duplicate_extra_rows": len(duplicate_rows),
            "animation_frame_rows": len(animation_rows),
            "animation_frame_groups": len(animation_group_rows),
            "animation_frame_extras": len(animation_exclusion_rows),
            "direct_path_exclusions": direct_path_count,
            "no_texture_candidates": no_texture_count,
            "temporary_review": temporary_count,
            "conservative_unique_exclusions": len(conservative_rows),
        },
        "duplicate_relations": dict(duplicate_relations.most_common()),
        "previous_tier_cross": dict(previous_tier_cross.most_common()),
        "net_outside_previous_p0_p1": net_outside_previous_p0_p1,
        "path_reason_counts": dict(path_reason_counts.most_common()),
        "concentrated_repositories": concentrated,
        "metadata_counts": dict(metadata_counts),
        "caption_exact_duplicate_groups": sum(count > 1 for count in caption_counts.values()),
    }

    write_csv(args.out_dir / "exact_duplicate_exclusions.csv", duplicate_rows, OUTPUT_FIELDS)
    write_csv(args.out_dir / "path_quality_candidates.csv", path_rows, OUTPUT_FIELDS)
    write_csv(args.out_dir / "animation_frame_candidates.csv", animation_exclusion_rows, OUTPUT_FIELDS)
    write_csv(args.out_dir / "conservative_unique_exclusions.csv", conservative_rows, OUTPUT_FIELDS)
    write_csv(
        args.out_dir / "animation_groups.csv",
        animation_group_rows,
        ("group", "row_count", "recommended_exclusions_if_keep_one", "representative_path"),
    )
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "summary.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps(summary["totals"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
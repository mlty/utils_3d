#!/usr/bin/env python3
"""Build an expanded exclusion set from existing quality analysis results."""

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
POLICY_REASONS = {
    "explicit_ai_generated",
    "scan_photogrammetry",
    "flat_or_proxy",
    "broken_fragment",
    "lod_or_optimized",
    "terrain_or_rock",
    "test_or_sample_asset",
    "billboard_or_sprite",
    "body_part",
    "sculpture_or_statue",
}
PRIMARY_ORDER = (
    "explicit_ai_generated",
    "scan_photogrammetry",
    "flat_or_proxy",
    "broken_fragment",
    "sculpture_or_statue",
    "body_part",
    "billboard_or_sprite",
    "test_or_sample_asset",
    "terrain_or_rock",
    "lod_or_optimized",
)
SCULPTURE_PATTERN = re.compile(r"\b(sculpture|statue|bust)\b|雕塑|雕像|半身像", re.IGNORECASE)
OUTPUT_FIELDS = (
    "dataset", "source_row", "sha256", "local_path", "file_identifier",
    "expanded_decision", "primary_reason", "all_policy_reasons", "original_decision",
    "original_reasons", "aesthetic_score", "face_count", "max_texture", "voxel_blocks",
    "reference_matched", "text_evidence",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).with_name("expanded_quality_exclusions"),
    )
    return parser.parse_args()


def iter_rows(input_dir: Path) -> Iterator[dict[str, str]]:
    for decision in ("reject", "review", "keep"):
        with (input_dir / f"{decision}_candidates.csv").open(
            encoding="utf-8-sig", errors="replace", newline=""
        ) as handle:
            yield from csv.DictReader(handle)


def policy_reasons(row: dict[str, str]) -> set[str]:
    reasons = {reason for reason in row["reasons"].split(";") if reason}
    if SCULPTURE_PATTERN.search(row.get("text_evidence", "")):
        reasons.add("sculpture_or_statue")
    return reasons & POLICY_REASONS


def primary_reason(reasons: set[str]) -> str:
    return next(reason for reason in PRIMARY_ORDER if reason in reasons)


def percentage(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total else "0.00%"


def build_report(summary: dict[str, object]) -> str:
    total = summary["total_input_rows"]
    excluded = summary["unique_exclusion_rows"]
    lines = [
        "# 扩展低质量撤出策略", "",
        "## 汇总", "",
        f"- 输入总数：{total:,}",
        f"- 去重后的扩展撤出候选：{excluded:,}（{percentage(excluded, total)}）",
        f"- 原 Reject：{summary['original_reject_rows']:,}",
        f"- 本策略新增：{summary['newly_added_rows']:,}",
        "- `very_low_voxel_blocks` 未单独纳入：0 块记录主要是处理失败，不等于低质量。",
        "", "## 各数据源", "",
        "| 数据源 | 原总数 | 扩展撤出 | 剩余 | 占该源比例 |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    for dataset, source_total in summary["dataset_totals"].items():
        count = summary["dataset_exclusions"].get(dataset, 0)
        remaining = summary["dataset_remaining"][dataset]
        lines.append(f"| {dataset} | {source_total:,} | {count:,} | {remaining:,} | {percentage(count, source_total)} |")

    lines.extend([
        "", "## 互斥主原因", "",
        "每条数据只归到优先级最高的一个主原因，因此本表可直接相加。", "",
        "| 主原因 | 数量 | 总体占比 |", "| --- | ---: | ---: |",
    ])
    for reason in PRIMARY_ORDER:
        count = summary["primary_reason_counts"].get(reason, 0)
        lines.append(f"| `{reason}` | {count:,} | {percentage(count, total)} |")

    lines.extend([
        "", "## 原因命中次数", "",
        "同一条数据可能命中多个原因，本表不能直接相加。", "",
        "| 原因 | 命中数据数 |", "| --- | ---: |",
    ])
    for reason, count in summary["reason_membership_counts"].items():
        lines.append(f"| `{reason}` | {count:,} |")

    lines.extend(["", "## 数据源 × 主原因", "", "| 数据源 | " + " | ".join(f"`{reason}`" for reason in PRIMARY_ORDER) + " |"])
    lines.append("| --- | " + " | ".join("---:" for _ in PRIMARY_ORDER) + " |")
    for dataset, counts in summary["dataset_primary_counts"].items():
        lines.append(f"| {dataset} | " + " | ".join(f"{counts.get(reason, 0):,}" for reason in PRIMARY_ORDER) + " |")

    lines.extend([
        "", "## 执行说明", "",
        "- 这是按当前策略生成的撤出候选集合，尚未修改五份原 CSV。",
        "- AI、扫描、代理/占位通常具有较强撤出依据。",
        "- LOD、地形、测试样本、广告牌、身体部件和雕塑属于训练范围策略，不一定是模型制作质量差。",
        "- `broken_fragment` 可能包含完整的废墟或刻意战损资产；若追求精度，删除前仍建议渲染核验。",
        "- 原因统计按样本集合计算，不与精确重复去重清单混合。跨数据源完全相同的 SHA 可另外执行 D0 去重。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    dataset_totals: Counter[str] = Counter()
    dataset_exclusions: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    membership_counts: Counter[str] = Counter()
    dataset_primary: dict[str, Counter[str]] = defaultdict(Counter)
    original_reject = 0
    newly_added = 0
    output_rows = 0
    exclusion_rows_by_dataset: dict[str, set[int]] = defaultdict(set)

    output_path = args.out_dir / "expanded_exclusion_candidates.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_handle:
        writer = csv.DictWriter(output_handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in iter_rows(args.input_dir):
            dataset = row["dataset"]
            dataset_totals[dataset] += 1
            reasons = policy_reasons(row)
            if not reasons:
                continue
            primary = primary_reason(reasons)
            output_rows += 1
            exclusion_rows_by_dataset[dataset].add(int(row["source_row"]))
            dataset_exclusions[dataset] += 1
            primary_counts[primary] += 1
            membership_counts.update(reasons)
            dataset_primary[dataset][primary] += 1
            if row["decision"] == "reject":
                original_reject += 1
            else:
                newly_added += 1
            writer.writerow({
                "dataset": dataset,
                "source_row": row["source_row"],
                "sha256": row["sha256"],
                "local_path": row["local_path"],
                "file_identifier": row["file_identifier"],
                "expanded_decision": "exclude",
                "primary_reason": primary,
                "all_policy_reasons": ";".join(reason for reason in PRIMARY_ORDER if reason in reasons),
                "original_decision": row["decision"],
                "original_reasons": row["reasons"],
                "aesthetic_score": row["aesthetic_score"],
                "face_count": row["face_count"],
                "max_texture": row["max_texture"],
                "voxel_blocks": row["voxel_blocks"],
                "reference_matched": row["reference_matched"],
                "text_evidence": row["text_evidence"],
            })

    filtered_dir = args.out_dir / "filtered"
    filtered_dir.mkdir(parents=True, exist_ok=True)
    filtered_counts: dict[str, int] = {}
    filtered_files: dict[str, str] = {}
    for dataset, input_path in DEFAULT_INPUTS:
        output_filtered = filtered_dir / f"{input_path.stem}_expanded_filtered.csv"
        excluded_rows = exclusion_rows_by_dataset[dataset]
        kept = 0
        with input_path.open(encoding="utf-8-sig", errors="replace", newline="") as input_handle:
            reader = csv.DictReader(input_handle)
            with output_filtered.open("w", encoding="utf-8-sig", newline="") as output_handle:
                writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames or [])
                writer.writeheader()
                for row_number, row in enumerate(reader, start=1):
                    if row_number in excluded_rows:
                        continue
                    writer.writerow(row)
                    kept += 1
        filtered_counts[dataset] = kept
        filtered_files[dataset] = str(output_filtered)

    summary = {
        "total_input_rows": sum(dataset_totals.values()),
        "unique_exclusion_rows": output_rows,
        "original_reject_rows": original_reject,
        "newly_added_rows": newly_added,
        "dataset_totals": dict(dataset_totals),
        "dataset_exclusions": dict(dataset_exclusions),
        "dataset_remaining": filtered_counts,
        "filtered_files": filtered_files,
        "primary_reason_counts": dict(primary_counts),
        "reason_membership_counts": dict(membership_counts.most_common()),
        "dataset_primary_counts": {dataset: dict(counts) for dataset, counts in dataset_primary.items()},
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "summary.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
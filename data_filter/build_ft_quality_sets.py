#!/usr/bin/env python3
"""Build strict and standard high-quality fine-tuning candidate sets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterator


OUTPUT_FIELDS = (
    "ft_tier", "dataset", "source_row", "sha256", "local_path", "file_identifier",
    "aesthetic_score", "face_count", "max_texture", "voxel_blocks", "selection_basis",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument(
        "--expanded-exclusions",
        type=Path,
        default=Path(__file__).with_name("expanded_quality_exclusions") / "expanded_exclusion_candidates.csv",
    )
    parser.add_argument(
        "--redundancy-exclusions",
        type=Path,
        default=Path(__file__).with_name("training_exclusion_analysis") / "conservative_unique_exclusions.csv",
    )
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("ft_quality_sets"))
    parser.add_argument("--strict-aesthetic", type=float, default=6.2)
    parser.add_argument("--standard-aesthetic", type=float, default=5.8)
    return parser.parse_args()


def iter_analysis_rows(analysis_dir: Path) -> Iterator[dict[str, str]]:
    for decision in ("reject", "review", "keep"):
        with (analysis_dir / f"{decision}_candidates.csv").open(
            encoding="utf-8-sig", errors="replace", newline=""
        ) as handle:
            yield from csv.DictReader(handle)


def load_keys(path: Path) -> set[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return {(row["dataset"], row["source_row"]) for row in csv.DictReader(handle)}


def number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def in_range(value: float | None, lower: float, upper: float) -> bool:
    return value is not None and lower <= value <= upper


def standard_eligible(row: dict[str, str], aesthetic_threshold: float) -> tuple[bool, str]:
    dataset = row["dataset"]
    blocks = number(row["voxel_blocks"])
    if not in_range(blocks, 1_000, 40_000):
        return False, ""
    if dataset in {"github", "sket"}:
        score = number(row["aesthetic_score"])
        return (score is not None and score >= aesthetic_threshold), f"aesthetic>={aesthetic_threshold};blocks=1000-40000"
    if dataset == "tex":
        faces = number(row["face_count"])
        texture = number(row["max_texture"])
        eligible = in_range(faces, 2_000, 1_000_000) and texture is not None and texture >= 1_024
        return eligible, "faces=2000-1000000;texture>=1024;blocks=1000-40000"
    if dataset in {"cg", "step1x"}:
        return in_range(blocks, 5_000, 30_000), "metadata_limited;blocks=5000-30000"
    return False, ""


def strict_eligible(row: dict[str, str], aesthetic_threshold: float) -> tuple[bool, str]:
    dataset = row["dataset"]
    blocks = number(row["voxel_blocks"])
    if not in_range(blocks, 2_000, 30_000):
        return False, ""
    if dataset in {"github", "sket"}:
        score = number(row["aesthetic_score"])
        matched = row.get("reference_matched", "").lower() == "true"
        eligible = matched and score is not None and score >= aesthetic_threshold
        return eligible, f"reference_matched;aesthetic>={aesthetic_threshold};blocks=2000-30000"
    if dataset == "tex":
        faces = number(row["face_count"])
        texture = number(row["max_texture"])
        eligible = in_range(faces, 5_000, 500_000) and texture is not None and texture >= 2_048
        return eligible, "faces=5000-500000;texture>=2048;blocks=2000-30000"
    return False, ""


def write_report(summary: dict[str, object], path: Path) -> None:
    funnel = summary["funnel"]
    lines = [
        "# 高质量 FT 精选集", "",
        "## 选择原则", "",
        "- 两档都要求原始质量决策为 Keep。",
        "- 排除 AI、扫描、破损、代理、LOD、地形、测试样本、广告牌、身体部件和雕塑。",
        "- 排除精确重复副本、动作逐帧冗余和明确低价值路径。",
        "- 排除体素化失败和复杂度极端样本。",
        "- GitHub/Sketchfab 使用审美分；TexVerse 使用面数和纹理分辨率；CG/Step1X 因证据有限只进入 Standard。",
        "", "## 筛选漏斗", "",
        "| 阶段 | 数量 |", "| --- | ---: |",
    ]
    for stage, count in funnel.items():
        lines.append(f"| `{stage}` | {count:,} |")
    lines.extend(["", "## 各来源入选数量", "", "| 来源 | Strict | Standard（含 Strict） |", "| --- | ---: | ---: |"])
    datasets = ("tex", "github", "sket", "cg", "step1x")
    for dataset in datasets:
        lines.append(
            f"| {dataset} | {summary['strict_by_dataset'].get(dataset, 0):,} | "
            f"{summary['standard_by_dataset'].get(dataset, 0):,} |"
        )
    lines.extend([
        "", "## 来源均衡 Strict", "",
        f"- 每个来源选择 {summary['balanced_per_dataset']:,} 条，共 {summary['balanced_total']:,} 条。",
        "- 仅平衡 Tex/GitHub/Sketchfab，使用 SHA256 固定排序，可重复生成。",
        "- 均衡解决来源占比，不解决语义类别占比；正式 FT 前仍建议按类别再平衡。",
    ])
    lines.extend([
        "", "## 建议", "",
        "- 首次高质量 FT 优先使用 Strict，并按来源和语义类别做均衡采样。",
        "- 数据量不足时逐步加入 Standard-only，不要一开始混入全部 Standard。",
        "- CG/Step1X 缺少审美分、caption 或完整几何纹理指标，建议渲染抽检后再用于关键 FT。",
        "- 当前精选仍是元数据级筛选；最终高质量集应增加多视角渲染、主体完整性、材质和法线检查。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    expanded_keys = load_keys(args.expanded_exclusions)
    redundancy_keys = load_keys(args.redundancy_exclusions)
    funnel: Counter[str] = Counter()
    strict_by_dataset: Counter[str] = Counter()
    standard_by_dataset: Counter[str] = Counter()

    strict_path = args.out_dir / "strict_ft_candidates.csv"
    standard_path = args.out_dir / "standard_ft_candidates.csv"
    with strict_path.open("w", encoding="utf-8-sig", newline="") as strict_handle, standard_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as standard_handle:
        strict_writer = csv.DictWriter(strict_handle, fieldnames=OUTPUT_FIELDS)
        standard_writer = csv.DictWriter(standard_handle, fieldnames=OUTPUT_FIELDS)
        strict_writer.writeheader()
        standard_writer.writeheader()
        for row in iter_analysis_rows(args.analysis_dir):
            funnel["input"] += 1
            key = (row["dataset"], row["source_row"])
            if row["decision"] != "keep":
                continue
            funnel["original_keep"] += 1
            if key in expanded_keys:
                continue
            funnel["after_semantic_policy"] += 1
            if key in redundancy_keys:
                continue
            funnel["after_redundancy_filter"] += 1

            standard, standard_basis = standard_eligible(row, args.standard_aesthetic)
            strict, strict_basis = strict_eligible(row, args.strict_aesthetic)
            if standard:
                standard_by_dataset[row["dataset"]] += 1
                funnel["standard"] += 1
                standard_writer.writerow({
                    "ft_tier": "strict" if strict else "standard_only",
                    **{field: row.get(field, "") for field in OUTPUT_FIELDS if field not in {"ft_tier", "selection_basis"}},
                    "selection_basis": strict_basis if strict else standard_basis,
                })
            if strict:
                strict_by_dataset[row["dataset"]] += 1
                funnel["strict"] += 1
                strict_writer.writerow({
                    "ft_tier": "strict",
                    **{field: row.get(field, "") for field in OUTPUT_FIELDS if field not in {"ft_tier", "selection_basis"}},
                    "selection_basis": strict_basis,
                })

    summary = {
        "thresholds": {
            "strict_aesthetic": args.strict_aesthetic,
            "standard_aesthetic": args.standard_aesthetic,
        },
        "funnel": dict(funnel),
        "strict_by_dataset": dict(strict_by_dataset),
        "standard_by_dataset": dict(standard_by_dataset),
    }
    strict_groups: dict[str, list[dict[str, str]]] = {dataset: [] for dataset in ("tex", "github", "sket")}
    with strict_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            strict_groups[row["dataset"]].append(row)
    balanced_per_dataset = min(len(rows) for rows in strict_groups.values())
    balanced_path = args.out_dir / "balanced_strict_ft_candidates.csv"
    with balanced_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for dataset in ("tex", "github", "sket"):
            ranked = sorted(
                strict_groups[dataset],
                key=lambda row: hashlib.sha256(f"ft-balance-v1:{row['sha256']}".encode()).digest(),
            )
            writer.writerows(ranked[:balanced_per_dataset])
    summary["balanced_per_dataset"] = balanced_per_dataset
    summary["balanced_total"] = balanced_per_dataset * len(strict_groups)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, args.out_dir / "summary.md")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
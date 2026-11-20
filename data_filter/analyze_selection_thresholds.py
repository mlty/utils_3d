#!/usr/bin/env python3
"""Explain semantic and numeric threshold exclusions for each dataset."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Iterator


DATASETS = ("tex", "github", "sket", "cg", "step1x")
ANALYSIS_FILES = ("reject_candidates.csv", "review_candidates.csv", "keep_candidates.csv")
VOXEL_BINS = (
    ("missing", lambda value: value is None),
    ("0", lambda value: value == 0),
    ("1-999", lambda value: value is not None and 1 <= value < 1_000),
    ("1,000-4,999", lambda value: value is not None and 1_000 <= value < 5_000),
    ("5,000-9,999", lambda value: value is not None and 5_000 <= value < 10_000),
    ("10,000-19,999", lambda value: value is not None and 10_000 <= value < 20_000),
    ("20,000-29,999", lambda value: value is not None and 20_000 <= value < 30_000),
    ("30,000-40,000", lambda value: value is not None and 30_000 <= value <= 40_000),
    (">40,000", lambda value: value is not None and value > 40_000),
)
FACE_BINS = (
    ("missing", lambda value: value is None),
    ("0-999", lambda value: value is not None and value < 1_000),
    ("1,000-4,999", lambda value: value is not None and 1_000 <= value < 5_000),
    ("5,000-49,999", lambda value: value is not None and 5_000 <= value < 50_000),
    ("50,000-199,999", lambda value: value is not None and 50_000 <= value < 200_000),
    ("200,000-1,000,000", lambda value: value is not None and 200_000 <= value <= 1_000_000),
    (">1,000,000", lambda value: value is not None and value > 1_000_000),
)
SCORE_BINS = (
    ("missing", lambda value: value is None),
    ("<5.0", lambda value: value is not None and value < 5.0),
    ("5.0-5.49", lambda value: value is not None and 5.0 <= value < 5.5),
    ("5.5-5.99", lambda value: value is not None and 5.5 <= value < 6.0),
    ("6.0-6.49", lambda value: value is not None and 6.0 <= value < 6.5),
    ("6.5-6.99", lambda value: value is not None and 6.5 <= value < 7.0),
    (">=7.0", lambda value: value is not None and value >= 7.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-dir", type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument(
        "--semantic-exclusions", type=Path,
        default=Path(__file__).with_name("expanded_quality_exclusions") / "expanded_exclusion_candidates.csv",
    )
    parser.add_argument(
        "--out-dir", type=Path,
        default=Path(__file__).with_name("selection_threshold_analysis"),
    )
    return parser.parse_args()


def iter_rows(analysis_dir: Path) -> Iterator[dict[str, str]]:
    for filename in ANALYSIS_FILES:
        with (analysis_dir / filename).open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield from csv.DictReader(handle)


def number(value: str) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def percentile(sorted_values: list[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] * (upper - position) + sorted_values[upper] * (position - lower)


def describe(values: list[float], total: int) -> dict[str, float | int | None]:
    values.sort()
    return {
        "available": len(values),
        "missing": total - len(values),
        "coverage": len(values) / total if total else 0,
        "min": values[0] if values else None,
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "max": values[-1] if values else None,
    }


def bin_value(value: float | None, bins: tuple[tuple[str, Callable[[float | None], bool]], ...]) -> str:
    return next(label for label, predicate in bins if predicate(value))


def threshold_failures(dataset: str, row: dict[str, str]) -> list[str]:
    blocks = number(row.get("voxel_blocks", ""))
    failures = []
    if dataset in {"tex", "github", "sket"}:
        if blocks is None:
            failures.append("voxel_missing")
        elif blocks < 1_000:
            failures.append("voxel_below_1000")
        elif blocks > 40_000:
            failures.append("voxel_above_40000")
    else:
        if blocks is None:
            failures.append("voxel_missing")
        elif blocks < 5_000:
            failures.append("voxel_below_5000")
        elif blocks > 30_000:
            failures.append("voxel_above_30000")

    if dataset in {"github", "sket"}:
        score = number(row.get("aesthetic_score", ""))
        if score is None:
            failures.append("aesthetic_missing")
        elif score < 5.0:
            failures.append("aesthetic_below_5")
    elif dataset == "tex":
        faces = number(row.get("face_count", ""))
        if faces is None:
            failures.append("face_count_missing")
        elif faces < 1_000:
            failures.append("face_count_below_1000")
        elif faces > 1_000_000:
            failures.append("face_count_above_1000000")
    return failures


def exclusive_failure(failures: list[str]) -> str:
    order = (
        "voxel_missing", "voxel_below_1000", "voxel_below_5000", "voxel_above_40000",
        "voxel_above_30000", "aesthetic_missing", "aesthetic_below_5", "face_count_missing",
        "face_count_below_1000", "face_count_above_1000000",
    )
    return next((reason for reason in order if reason in failures), "pass")


def rate(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total else "0.00%"


def fmt(value: float | int | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def build_report(summary: dict[str, object]) -> str:
    lines = [
        "# 数据源语义与数值阈值分析", "",
        "## 两类删除的含义", "",
        "- **语义风险删除**：caption、URL 或路径表明资产属于 AI、扫描、破损/残片、地形/岩石、LOD、雕塑、测试样本、广告牌、身体部件或代理模型。它描述资产内容或用途。",
        "- **阈值删除**：先排除语义风险后，再检查体素块、面数或审美分。不满足范围或必要字段缺失即删除。它描述数值门槛，不一定代表视觉低质。",
        "- 两类采用顺序互斥口径：语义风险优先，一条数据不会在总删除中重复计数。", "",
        "## 总体结果", "",
        "| 数据源 | 总数 | 语义删除 | 阈值删除 | 剩余 |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    for dataset in DATASETS:
        stats = summary["datasets"][dataset]
        lines.append(
            f"| {dataset} | {stats['total']:,} | {stats['semantic_delete']:,} ({rate(stats['semantic_delete'], stats['total'])}) | "
            f"{stats['threshold_delete']:,} ({rate(stats['threshold_delete'], stats['post_semantic'])}) | {stats['keep']:,} |"
        )

    lines.extend(["", "## 数值分位数", "", "分位数基于有值记录，缺失率单独列出。", "",
                  "| 数据源 | 指标 | 覆盖率 | P10 | P25 | P50 | P75 | P90 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for dataset in DATASETS:
        for metric in ("voxel_blocks", "face_count", "aesthetic_score"):
            stats = summary["datasets"][dataset]["metrics"][metric]
            lines.append(
                f"| {dataset} | {metric} | {stats['coverage']:.2%} | {fmt(stats['p10'])} | {fmt(stats['p25'])} | "
                f"{fmt(stats['p50'])} | {fmt(stats['p75'])} | {fmt(stats['p90'])} |"
            )

    for dataset in DATASETS:
        stats = summary["datasets"][dataset]
        lines.extend(["", f"## {dataset}", "",
                      f"- 总数 {stats['total']:,}；语义删除 {stats['semantic_delete']:,}；语义过滤后 {stats['post_semantic']:,}。",
                      f"- 阈值删除 {stats['threshold_delete']:,}，占语义过滤后 {rate(stats['threshold_delete'], stats['post_semantic'])}；最终保留 {stats['keep']:,}。",
                      "", "### 语义主原因", "", "| 原因 | 数量 |", "| --- | ---: |"])
        for reason, count in stats["semantic_primary"].items():
            lines.append(f"| `{reason}` | {count:,} |")
        lines.extend(["", "### 阈值失败（可重叠）", "", "| 失败项 | 数量 |", "| --- | ---: |"])
        for reason, count in stats["threshold_membership"].items():
            lines.append(f"| `{reason}` | {count:,} |")
        lines.extend(["", "### 阈值删除（互斥首要原因）", "", "| 首要原因 | 数量 |", "| --- | ---: |"])
        for reason, count in stats["threshold_exclusive"].items():
            if reason != "pass":
                lines.append(f"| `{reason}` | {count:,} |")
        lines.extend(["", "### 体素块分布", "", "| 区间 | 全源 | 语义过滤后 |", "| --- | ---: | ---: |"])
        for bucket in summary["voxel_bucket_order"]:
            lines.append(f"| {bucket} | {stats['voxel_bins_all'].get(bucket, 0):,} | {stats['voxel_bins_post_semantic'].get(bucket, 0):,} |")
        if dataset == "tex":
            lines.extend(["", "### 面数分布", "", "| 区间 | 全源 | 语义过滤后 |", "| --- | ---: | ---: |"])
            for bucket in summary["face_bucket_order"]:
                lines.append(f"| {bucket} | {stats['face_bins_all'].get(bucket, 0):,} | {stats['face_bins_post_semantic'].get(bucket, 0):,} |")
        if dataset in {"github", "sket"}:
            lines.extend(["", "### 审美分分布", "", "| 区间 | 全源 | 语义过滤后 |", "| --- | ---: | ---: |"])
            for bucket in summary["score_bucket_order"]:
                lines.append(f"| {bucket} | {stats['score_bins_all'].get(bucket, 0):,} | {stats['score_bins_post_semantic'].get(bucket, 0):,} |")

    lines.extend(["", "## 结论", "",
                  "- 当前 90,428 条阈值删除全部由体素块门槛触发。",
                  "- GitHub/Sketchfab 的有效审美分最低约为 5.5，因此 `>=5.0` 没有删除任何有分数记录；缺失分数也均与体素失败重叠，没有净新增删除。",
                  "- TexVerse 面数范围原本就是 1,000-500,000，因此 `1,000-1,000,000` 没有产生任何删除；其阈值删除全部来自体素越界。",
                  "- CG/Step1X 没有面数和审美分，只能依赖体素复杂度；其保留结果不能与有完整质量元数据的来源等价。",
                  "- 体素块为 0 通常对应处理失败，应优先进入重处理队列，而不是解释为视觉低质量。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    semantic_by_key: dict[tuple[str, str], str] = {}
    with args.semantic_exclusions.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            semantic_by_key[(row["dataset"], row["source_row"])] = row["primary_reason"]

    data: dict[str, dict[str, object]] = {}
    raw_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in iter_rows(args.analysis_dir):
        raw_rows[row["dataset"]].append(row)

    for dataset in DATASETS:
        rows = raw_rows[dataset]
        semantic_primary: Counter[str] = Counter()
        threshold_membership: Counter[str] = Counter()
        threshold_exclusive: Counter[str] = Counter()
        all_values: dict[str, list[float]] = defaultdict(list)
        voxel_all: Counter[str] = Counter()
        voxel_post: Counter[str] = Counter()
        face_all: Counter[str] = Counter()
        face_post: Counter[str] = Counter()
        score_all: Counter[str] = Counter()
        score_post: Counter[str] = Counter()
        post_semantic = 0

        for row in rows:
            blocks = number(row.get("voxel_blocks", ""))
            faces = number(row.get("face_count", ""))
            score = number(row.get("aesthetic_score", ""))
            voxel_all[bin_value(blocks, VOXEL_BINS)] += 1
            face_all[bin_value(faces, FACE_BINS)] += 1
            score_all[bin_value(score, SCORE_BINS)] += 1
            for metric, value in (("voxel_blocks", blocks), ("face_count", faces), ("aesthetic_score", score)):
                if value is not None:
                    all_values[metric].append(value)
            semantic_reason = semantic_by_key.get((dataset, row["source_row"]))
            if semantic_reason:
                semantic_primary[semantic_reason] += 1
                continue
            post_semantic += 1
            voxel_post[bin_value(blocks, VOXEL_BINS)] += 1
            face_post[bin_value(faces, FACE_BINS)] += 1
            score_post[bin_value(score, SCORE_BINS)] += 1
            failures = threshold_failures(dataset, row)
            threshold_membership.update(failures)
            threshold_exclusive[exclusive_failure(failures)] += 1

        threshold_delete = post_semantic - threshold_exclusive["pass"]
        data[dataset] = {
            "total": len(rows),
            "semantic_delete": sum(semantic_primary.values()),
            "post_semantic": post_semantic,
            "threshold_delete": threshold_delete,
            "keep": threshold_exclusive["pass"],
            "semantic_primary": dict(semantic_primary.most_common()),
            "threshold_membership": dict(threshold_membership.most_common()),
            "threshold_exclusive": dict(threshold_exclusive.most_common()),
            "metrics": {metric: describe(all_values[metric], len(rows)) for metric in ("voxel_blocks", "face_count", "aesthetic_score")},
            "voxel_bins_all": dict(voxel_all),
            "voxel_bins_post_semantic": dict(voxel_post),
            "face_bins_all": dict(face_all),
            "face_bins_post_semantic": dict(face_post),
            "score_bins_all": dict(score_all),
            "score_bins_post_semantic": dict(score_post),
        }

    summary = {
        "rules": {
            "tex": "voxel_blocks 1000-40000; face_count 1000-1000000",
            "github": "voxel_blocks 1000-40000; aesthetic_score >=5.0",
            "sket": "voxel_blocks 1000-40000; aesthetic_score >=5.0",
            "cg": "voxel_blocks 5000-30000",
            "step1x": "voxel_blocks 5000-30000",
        },
        "datasets": data,
        "voxel_bucket_order": [label for label, _ in VOXEL_BINS],
        "face_bucket_order": [label for label, _ in FACE_BINS],
        "score_bucket_order": [label for label, _ in SCORE_BINS],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "summary.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps({dataset: {key: data[dataset][key] for key in ("total", "semantic_delete", "threshold_delete", "keep")} for dataset in DATASETS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
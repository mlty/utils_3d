#!/usr/bin/env python3
"""Build detailed, mutually exclusive triage statistics from quality candidates."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator


DECISIONS = ("reject", "review", "keep")
HARD_REASONS = {"explicit_ai_generated", "scan_photogrammetry", "flat_or_proxy", "broken_fragment"}
DIRECT_REMOVE_REASONS = {"explicit_ai_generated", "flat_or_proxy"}
POLICY_REASONS = {"terrain_or_rock", "lod_or_optimized", "test_or_sample_asset", "billboard_or_sprite", "body_part"}
OUTPUT_FIELDS = (
    "priority", "priority_explanation", "dataset", "source_row", "sha256", "local_path",
    "file_identifier", "decision", "reasons", "aesthetic_score", "face_count", "max_texture",
    "voxel_blocks", "reference_matched", "text_evidence",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).with_name("removed_metadata_analysis"),
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def parse_number(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] * (upper - position) + values[upper] * (position - lower)


def iter_candidates(input_dir: Path) -> Iterator[dict[str, str]]:
    for decision in DECISIONS:
        path = input_dir / f"{decision}_candidates.csv"
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield from csv.DictReader(handle)


def reason_set(row: dict[str, str]) -> set[str]:
    return {reason for reason in row.get("reasons", "").split(";") if reason}


def classify_priority(row: dict[str, str]) -> tuple[str, str]:
    reasons = reason_set(row)
    blocks = parse_number(row.get("voxel_blocks", ""))
    hard = reasons & HARD_REASONS
    weak = reasons - HARD_REASONS

    if reasons & DIRECT_REMOVE_REASONS:
        return "P0", "显式 AI 或代理/占位模型，高置信删除候选"
    if "scan_photogrammetry" in reasons:
        return "P0", "扫描/摄影测量资产；若训练目标排除扫描数据则删除"
    if "broken_fragment" in reasons and (weak or len(hard) > 1):
        return "P1", "破损/残片信号叠加其他风险，优先渲染复核"
    if "broken_fragment" in reasons:
        return "P1", "仅文本出现破损描述，可能是刻意做旧，需渲染确认"
    if blocks == 0:
        return "REPROCESS", "体素块为 0 且原始 block status 为 failed，应修复或重试处理链"
    if len(reasons) >= 3 or (blocks is not None and blocks <= 16):
        return "P1", "三个以上弱信号或非零体素块不超过 16，优先复核"
    if len(reasons) >= 2 or (blocks is not None and blocks <= 64):
        return "P2", "两个弱信号或体素块不超过 64，建议分层抽检"
    if reasons & POLICY_REASONS or "very_low_voxel_blocks" in reasons:
        return "P3", "单一弱信号，按训练目标处理，不建议自动删除"
    return "KEEP", "当前元数据规则未发现风险"


def block_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value == 0:
        return "0"
    if value <= 16:
        return "1-16"
    if value <= 32:
        return "17-32"
    if value <= 64:
        return "33-64"
    if value <= 128:
        return "65-128"
    if value <= 1000:
        return "129-1000"
    if value <= 5000:
        return "1001-5000"
    return ">5000"


def score_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 4.5:
        return "<4.5"
    if value < 5:
        return "4.5-4.99"
    if value < 6:
        return "5.0-5.99"
    if value < 7:
        return "6.0-6.99"
    return ">=7.0"


def sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(counter.most_common())


def format_rate(count: int, total: int) -> str:
    return f"{count / total:.2%}" if total else "0.00%"


def format_number(value: float | None) -> str:
    return "-" if value is None else f"{value:,.1f}"


def build_report(summary: dict[str, Any]) -> str:
    total = summary["total"]
    priorities = summary["priorities"]
    lines = [
        "# Remove 后数据深度分析", "",
        "## 核心结论", "",
        f"- 总数据：{total:,}。P0 高置信处置 {priorities.get('P0', 0):,} 条，"
        f"P1 优先渲染复核 {priorities.get('P1', 0):,} 条。",
        f"- REPROCESS 工程失败队列 {priorities.get('REPROCESS', 0):,} 条；这些不是质量判负，应修复或重试体素化。",
        f"- P2 分层抽检 {priorities.get('P2', 0):,} 条，P3 单一弱信号 {priorities.get('P3', 0):,} 条。",
        f"- 无当前规则信号：{priorities.get('KEEP', 0):,} 条。Keep 不等于视觉验收通过。",
        "- 原始原因计数不是互斥样本数；本报告的优先级每条数据只计一次。", "",
        "## 互斥处置分层", "",
        "| 优先级 | 数量 | 总体占比 | 建议 |", "| --- | ---: | ---: | --- |",
    ]
    descriptions = {
        "P0": "显式 AI、代理/占位，或按策略排除扫描数据",
        "P1": "破损类、三个以上弱信号或非零体素块 <=16，先渲染",
        "REPROCESS": "体素块为 0 且处理失败，修复或重试，不应直接删除",
        "P2": "两个弱信号或体素块 <=64，分层抽检",
        "P3": "单一弱信号，按训练目标决定",
        "KEEP": "元数据未发现风险，仍需视觉抽样",
    }
    for priority in ("P0", "P1", "REPROCESS", "P2", "P3", "KEEP"):
        count = priorities.get(priority, 0)
        lines.append(f"| {priority} | {count:,} | {format_rate(count, total)} | {descriptions[priority]} |")

    lines.extend(["", "## 各数据源分层", "", "| 数据源 | P0 | P1 | REPROCESS | P2 | P3 | KEEP |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for dataset, counts in summary["dataset_priorities"].items():
        lines.append("| {} | {:,} | {:,} | {:,} | {:,} | {:,} | {:,} |".format(
            dataset, *(counts.get(priority, 0) for priority in ("P0", "P1", "REPROCESS", "P2", "P3", "KEEP"))
        ))

    lines.extend(["", "## Review 信号强度", "", "| 命中原因数 | 数量 | Review 占比 |", "| --- | ---: | ---: |"])
    review_total = summary["decision_counts"].get("review", 0)
    for count, amount in summary["review_reason_count"].items():
        lines.append(f"| {count} | {amount:,} | {format_rate(amount, review_total)} |")

    lines.extend(["", "## Review 主要原因组合", "", "| 原因组合 | 数量 |", "| --- | ---: |"])
    for combination, count in list(summary["review_combinations"].items())[:20]:
        lines.append(f"| `{combination}` | {count:,} |")

    lines.extend(["", "## Reject 构成", "", "| 硬原因组合 | 数量 |", "| --- | ---: |"])
    for combination, count in summary["reject_hard_combinations"].items():
        lines.append(f"| `{combination}` | {count:,} |")

    lines.extend(["", "## 体素块分布", "", "| 区间 | 全量 | Review | Reject |", "| --- | ---: | ---: | ---: |"])
    bucket_order = ("0", "1-16", "17-32", "33-64", "65-128", "129-1000", "1001-5000", ">5000", "missing")
    for bucket in bucket_order:
        lines.append(f"| {bucket} | {summary['block_buckets_all'].get(bucket, 0):,} | "
                     f"{summary['block_buckets_review'].get(bucket, 0):,} | {summary['block_buckets_reject'].get(bucket, 0):,} |")

    lines.extend(["", "## 审美分分布", "", "| 分数区间 | 全量 | Review | Reject |", "| --- | ---: | ---: | ---: |"])
    for bucket in ("<4.5", "4.5-4.99", "5.0-5.99", "6.0-6.99", ">=7.0", "missing"):
        lines.append(f"| {bucket} | {summary['score_buckets_all'].get(bucket, 0):,} | "
                     f"{summary['score_buckets_review'].get(bucket, 0):,} | {summary['score_buckets_reject'].get(bucket, 0):,} |")

    numeric = summary["numeric_summary"]
    lines.extend([
        "", "## 数值摘要", "",
        "| 指标 | 有值数量 | P10 | 中位数 | P90 |", "| --- | ---: | ---: | ---: | ---: |",
    ])
    for name, stats in numeric.items():
        lines.append(f"| {name} | {stats['count']:,} | {format_number(stats['p10'])} | "
                     f"{format_number(stats['p50'])} | {format_number(stats['p90'])} |")

    lines.extend([
        "", "## 解释与执行建议", "",
        "1. P0 不是无条件删除清单：显式 AI 和代理/占位可直接排除；扫描数据是否删除取决于训练目标。",
        "2. REPROCESS 的体素块均为 0，回查原始表后 block status 全部为 failed；这是工程处理失败，不是低质量结论。",
        "3. P1 中大量 `broken_fragment` 来自文字描述，可能是完整的废墟、做旧或战损资产，必须先看渲染。",
        "4. P2/P3 的低体素、LOD、地形和测试路径都是弱信号。低体素可能只是小而简单的有效物体，LOD 也可能是合格游戏资产。",
        "5. 先核验 P0 并渲染 P1；并行修复 REPROCESS；再从 P2 各原因组合等比例抽样。",
        "6. P3 仅在训练任务明确排除对应类别时批量处理；`missing` 不应被解释为质量差。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir or args.input_dir / "detail"
    out_dir.mkdir(parents=True, exist_ok=True)

    priority_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    dataset_priorities: dict[str, Counter[str]] = defaultdict(Counter)
    review_reason_count: Counter[str] = Counter()
    review_combinations: Counter[str] = Counter()
    reject_hard_combinations: Counter[str] = Counter()
    block_buckets_all: Counter[str] = Counter()
    block_buckets_review: Counter[str] = Counter()
    block_buckets_reject: Counter[str] = Counter()
    score_buckets_all: Counter[str] = Counter()
    score_buckets_review: Counter[str] = Counter()
    score_buckets_reject: Counter[str] = Counter()
    numeric_values: dict[str, list[float]] = defaultdict(list)

    handles = {
        priority: (out_dir / f"{priority.lower()}_candidates.csv").open("w", encoding="utf-8-sig", newline="")
        for priority in ("P0", "P1", "REPROCESS", "P2", "P3")
    }
    try:
        writers = {priority: csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS) for priority, handle in handles.items()}
        for writer in writers.values():
            writer.writeheader()

        for row in iter_candidates(args.input_dir):
            decision = row["decision"]
            reasons = reason_set(row)
            priority, explanation = classify_priority(row)
            priority_counts[priority] += 1
            decision_counts[decision] += 1
            dataset_priorities[row["dataset"]][priority] += 1

            blocks = parse_number(row.get("voxel_blocks", ""))
            score = parse_number(row.get("aesthetic_score", ""))
            block_buckets_all[block_bucket(blocks)] += 1
            score_buckets_all[score_bucket(score)] += 1
            for field in ("aesthetic_score", "face_count", "max_texture", "voxel_blocks"):
                value = parse_number(row.get(field, ""))
                if value is not None:
                    numeric_values[field].append(value)

            if decision == "review":
                review_reason_count[str(len(reasons))] += 1
                review_combinations[" + ".join(sorted(reasons))] += 1
                block_buckets_review[block_bucket(blocks)] += 1
                score_buckets_review[score_bucket(score)] += 1
            elif decision == "reject":
                reject_hard_combinations[" + ".join(sorted(reasons & HARD_REASONS))] += 1
                block_buckets_reject[block_bucket(blocks)] += 1
                score_buckets_reject[score_bucket(score)] += 1

            if priority in writers:
                writers[priority].writerow({
                    "priority": priority,
                    "priority_explanation": explanation,
                    **{field: row.get(field, "") for field in OUTPUT_FIELDS if field not in {"priority", "priority_explanation"}},
                })
    finally:
        for handle in handles.values():
            handle.close()

    numeric_summary = {}
    for field, values in numeric_values.items():
        values.sort()
        numeric_summary[field] = {
            "count": len(values),
            "p10": percentile(values, 0.1),
            "p50": percentile(values, 0.5),
            "p90": percentile(values, 0.9),
        }

    summary = {
        "total": sum(decision_counts.values()),
        "decision_counts": sorted_counter(decision_counts),
        "priorities": sorted_counter(priority_counts),
        "dataset_priorities": {dataset: dict(counts) for dataset, counts in dataset_priorities.items()},
        "review_reason_count": dict(sorted(review_reason_count.items(), key=lambda item: int(item[0]))),
        "review_combinations": sorted_counter(review_combinations),
        "reject_hard_combinations": sorted_counter(reject_hard_combinations),
        "block_buckets_all": dict(block_buckets_all),
        "block_buckets_review": dict(block_buckets_review),
        "block_buckets_reject": dict(block_buckets_reject),
        "score_buckets_all": dict(score_buckets_all),
        "score_buckets_review": dict(score_buckets_review),
        "score_buckets_reject": dict(score_buckets_reject),
        "numeric_summary": numeric_summary,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(build_report(summary), encoding="utf-8")
    print(json.dumps({"total": summary["total"], "priorities": summary["priorities"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
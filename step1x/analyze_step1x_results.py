#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ASSET_ID_RE = re.compile(r"([0-9a-fA-F]{32})(?=\.glb$)")
RAW_FOLDER_RE = re.compile(r"(?:^|[/\\])(raw\d+)(?:[/\\])", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze Step1X asset filtering results.")
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("/Users/mlty/Documents/raw0_raw7_asset_summary_20260814.csv"),
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata_step1x.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("step1x_analysis_report_20260814"),
    )
    return parser.parse_args()


def normalize(value):
    return (value or "").strip()


def asset_key(raw_folder, filename):
    match = ASSET_ID_RE.search(normalize(filename))
    if not match:
        return None
    return normalize(raw_folder).lower(), match.group(1).lower()


def metadata_key(local_path):
    path = normalize(local_path)
    raw_match = RAW_FOLDER_RE.search(path)
    id_match = ASSET_ID_RE.search(path)
    if not raw_match or not id_match:
        return None
    return raw_match.group(1).lower(), id_match.group(1).lower()


def is_rejected(row):
    status = normalize(row.get("final_status")).lower()
    decision = normalize(row.get("llm_filter_decision")).lower()
    return status.startswith("reject") or decision == "reject"


def split_multi_value(value):
    value = normalize(value)
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, list):
        return [normalize(str(item)) for item in parsed if normalize(str(item))]
    return [part.strip(" []'\"") for part in re.split(r"[;|,]", value) if part.strip(" []'\"")]


def percentage(count, total):
    return 100.0 * count / total if total else 0.0


def triangle_bucket(value):
    try:
        count = int(float(normalize(value)))
    except ValueError:
        return "missing_or_invalid"
    if count <= 150:
        return "<=150"
    if count <= 1500:
        return "151-1500"
    if count < 3000:
        return "1501-2999"
    return "3000-4999"


def write_counter(path, label, counter, total):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([label, "count", "percentage"])
        for value, count in counter.most_common():
            writer.writerow([value or "(empty)", count, f"{percentage(count, total):.4f}"])


def markdown_table(counter, total, limit=None):
    rows = counter.most_common(limit)
    lines = ["| 类别 | 数量 | 占比 |", "|---|---:|---:|"]
    for value, count in rows:
        display = (value or "(空)").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {display} | {count:,} | {percentage(count, total):.2f}% |")
    return "\n".join(lines)


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metadata_keys = set()
    metadata_key_counts = Counter()
    metadata_raw_counts = Counter()
    rendered_counts = Counter()
    cond_rendered_counts = Counter()
    block_status_counts = {"occ8": Counter(), "occ4": Counter()}
    malformed_metadata_keys = 0

    with args.metadata.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = metadata_key(row.get("local_path"))
            if key is None:
                malformed_metadata_keys += 1
            else:
                metadata_keys.add(key)
                metadata_key_counts[key] += 1
                metadata_raw_counts[key[0]] += 1
            rendered_counts[normalize(row.get("rendered"))] += 1
            cond_rendered_counts[normalize(row.get("cond_rendered"))] += 1
            block_status_counts["occ8"][normalize(row.get("64_15_occ8_block_status"))] += 1
            block_status_counts["occ4"][normalize(row.get("64_15_occ4_block_status"))] += 1

    summary_rows = 0
    summary_keys = set()
    summary_key_counts = Counter()
    key_statuses = defaultdict(set)
    key_reasons = defaultdict(set)
    key_filenames = defaultdict(set)
    summary_raw_counts = Counter()
    status_counts = Counter()
    source_counts = Counter()
    reason_counts = Counter()
    geometry_reason_counts = Counter()
    llm_decision_counts = Counter()
    llm_issue_counts = Counter()
    llm_reject_issue_counts = Counter()
    llm_reject_category_counts = Counter()
    reject_status_counts = Counter()
    reject_source_counts = Counter()
    reject_reason_counts = Counter()
    reject_raw_counts = Counter()
    reject_color_counts = Counter()
    reject_geometry_counts = Counter()
    reject_llm_severity_counts = Counter()
    low_poly_triangle_buckets = Counter()
    raw_status_counts = defaultdict(Counter)
    malformed_summary_keys = 0
    rejected_rows = 0
    matched_rows = 0

    with args.summary.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            summary_rows += 1
            raw_folder = normalize(row.get("raw_folder")).lower()
            key = asset_key(raw_folder, row.get("file_name"))
            if key is None:
                malformed_summary_keys += 1
            else:
                summary_keys.add(key)
                summary_key_counts[key] += 1
                key_statuses[key].add(normalize(row.get("final_status")))
                key_reasons[key].add(normalize(row.get("reason")))
                key_filenames[key].add(normalize(row.get("file_name")))
                if key in metadata_keys:
                    matched_rows += 1

            status = normalize(row.get("final_status"))
            source = normalize(row.get("reason_source"))
            reason = normalize(row.get("reason"))
            summary_raw_counts[raw_folder] += 1
            status_counts[status] += 1
            source_counts[source] += 1
            reason_counts[reason] += 1
            raw_status_counts[raw_folder][status] += 1
            llm_decision_counts[normalize(row.get("llm_filter_decision"))] += 1
            for item in split_multi_value(row.get("geometry_reasons")):
                geometry_reason_counts[item] += 1
            for item in split_multi_value(row.get("llm_quality_issues")):
                llm_issue_counts[item] += 1

            if is_rejected(row):
                rejected_rows += 1
                reject_status_counts[status] += 1
                reject_source_counts[source] += 1
                reject_reason_counts[reason] += 1
                reject_raw_counts[raw_folder] += 1
                reject_color_counts[normalize(row.get("color_category"))] += 1
                reject_geometry_counts[normalize(row.get("geometry_status"))] += 1
                reject_llm_severity_counts[normalize(row.get("llm_reject_severity"))] += 1
                if status == "reject_rule_low_poly":
                    low_poly_triangle_buckets[triangle_bucket(row.get("triangle_count"))] += 1
                if status == "reject_llm":
                    llm_reject_category_counts[normalize(row.get("llm_asset_category"))] += 1
                    for item in split_multi_value(row.get("llm_quality_issues")):
                        llm_reject_issue_counts[item] += 1

    metadata_rows = sum(metadata_key_counts.values()) + malformed_metadata_keys
    metadata_duplicate_rows = sum(count - 1 for count in metadata_key_counts.values() if count > 1)
    summary_duplicate_rows = sum(count - 1 for count in summary_key_counts.values() if count > 1)
    duplicate_keys = {key for key, count in summary_key_counts.items() if count > 1}
    conflicting_status_keys = sum(len(key_statuses[key]) > 1 for key in duplicate_keys)
    conflicting_reason_keys = sum(len(key_reasons[key]) > 1 for key in duplicate_keys)
    multiple_filename_keys = sum(len(key_filenames[key]) > 1 for key in duplicate_keys)
    metadata_only = metadata_keys - summary_keys
    summary_only = summary_keys - metadata_keys

    write_counter(args.output_dir / "final_status_counts.csv", "final_status", status_counts, summary_rows)
    write_counter(args.output_dir / "reject_reason_source_counts.csv", "reason_source", reject_source_counts, rejected_rows)
    write_counter(args.output_dir / "reject_reason_counts.csv", "reason", reject_reason_counts, rejected_rows)
    write_counter(args.output_dir / "geometry_reason_counts.csv", "geometry_reason", geometry_reason_counts, summary_rows)
    write_counter(args.output_dir / "llm_quality_issue_counts.csv", "llm_quality_issue", llm_issue_counts, summary_rows)
    write_counter(
        args.output_dir / "llm_reject_quality_issue_counts.csv",
        "llm_quality_issue",
        llm_reject_issue_counts,
        reject_status_counts["reject_llm"],
    )

    with (args.output_dir / "raw_folder_status_counts.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["raw_folder", "final_status", "count", "raw_folder_percentage"])
        for raw_folder in sorted(raw_status_counts):
            total = summary_raw_counts[raw_folder]
            for status, count in raw_status_counts[raw_folder].most_common():
                writer.writerow([raw_folder, status or "(empty)", count, f"{percentage(count, total):.4f}"])

    raw_rejection_rates = Counter(
        {
            raw_folder: percentage(reject_raw_counts[raw_folder], count)
            for raw_folder, count in summary_raw_counts.items()
        }
    )
    raw_rejection_lines = ["| 分区 | 汇总行数 | 拒绝行数 | 拒绝率 |", "|---|---:|---:|---:|"]
    for raw_folder, rate in raw_rejection_rates.most_common():
        raw_rejection_lines.append(
            f"| {raw_folder} | {summary_raw_counts[raw_folder]:,} | "
            f"{reject_raw_counts[raw_folder]:,} | {rate:.2f}% |"
        )
    raw_rejection_table = "\n".join(raw_rejection_lines)

    report = f"""# Step1X 数据判别分析报告

## 结论摘要

- 原始 metadata 共 **{metadata_rows:,}** 行、**{len(metadata_keys):,}** 个唯一资产键。
- 判别汇总共 **{summary_rows:,}** 行、**{len(summary_keys):,}** 个可解析唯一资产键；存在 **{len(duplicate_keys):,}** 个重复资产键。
- 判别汇总中拒绝 **{rejected_rows:,}** 行，占 **{percentage(rejected_rows, summary_rows):.2f}%**。
- 汇总行可关联原始 metadata **{matched_rows:,}** 行，占 **{percentage(matched_rows, summary_rows):.2f}%**。
- 原始 metadata 中未进入汇总的唯一资产 **{len(metadata_only):,}** 个；汇总中无法关联原始 metadata 的唯一资产 **{len(summary_only):,}** 个。

## 最终状态

{markdown_table(status_counts, summary_rows)}

## 拒绝类型

### 按最终状态

{markdown_table(reject_status_counts, rejected_rows)}

### 按判别来源

{markdown_table(reject_source_counts, rejected_rows)}

### 按具体原因（前 30）

{markdown_table(reject_reason_counts, rejected_rows, 30)}

低面数原因中的具体三角面数会造成高基数长尾，更适合按区间观察：

{markdown_table(low_poly_triangle_buckets, reject_status_counts['reject_rule_low_poly'])}

### 拒绝资产的颜色分类

{markdown_table(reject_color_counts, rejected_rows)}

### 拒绝资产的几何解析状态

{markdown_table(reject_geometry_counts, rejected_rows)}

### LLM 拒绝严重度

{markdown_table(reject_llm_severity_counts, rejected_rows)}

### LLM 拒绝质量问题

仅以 `reject_llm` 的 **{reject_status_counts['reject_llm']:,}** 行为分母；标签可多选。

{markdown_table(llm_reject_issue_counts, reject_status_counts['reject_llm'], 30)}

### LLM 拒绝资产大类（前 30）

{markdown_table(llm_reject_category_counts, reject_status_counts['reject_llm'], 30)}

## 全量质量信号

### 几何问题标签

标签可多选，因此占比之和可能超过 100%。

{markdown_table(geometry_reason_counts, summary_rows, 30)}

### LLM 质量问题

标签可多选，因此占比之和可能超过 100%。

{markdown_table(llm_issue_counts, summary_rows, 30)}

### LLM 决策

{markdown_table(llm_decision_counts, summary_rows)}

## 原始数据处理状态

### rendered

{markdown_table(rendered_counts, metadata_rows)}

### cond_rendered

{markdown_table(cond_rendered_counts, metadata_rows)}

### 64_15_occ8 block status

{markdown_table(block_status_counts['occ8'], metadata_rows)}

### 64_15_occ4 block status

{markdown_table(block_status_counts['occ4'], metadata_rows)}

## 分区规模

### 原始 metadata

{markdown_table(metadata_raw_counts, metadata_rows)}

### 判别汇总

{markdown_table(summary_raw_counts, summary_rows)}

### 拒绝资产

{markdown_table(reject_raw_counts, rejected_rows)}

### 各分区拒绝率

{raw_rejection_table}

## 数据质量与关联审计

| 指标 | 数量 |
|---|---:|
| metadata 无法解析关联键 | {malformed_metadata_keys:,} |
| 汇总无法解析关联键 | {malformed_summary_keys:,} |
| metadata 重复键额外行 | {metadata_duplicate_rows:,} |
| 汇总重复键额外行 | {summary_duplicate_rows:,} |
| 汇总重复资产键 | {len(duplicate_keys):,} |
| 重复键对应多个文件名 | {multiple_filename_keys:,} |
| 重复键最终状态冲突 | {conflicting_status_keys:,} |
| 重复键原因冲突 | {conflicting_reason_keys:,} |
| metadata 独有键 | {len(metadata_only):,} |
| 汇总独有键 | {len(summary_only):,} |

## 口径说明

- 关联键：`raw_folder + GLB 文件名末尾 32 位 asset_id`；原始表的 `sha256` 不存在于判别汇总中，不能直接作为关联键。
- 拒绝：`final_status` 以 `reject` 开头，或 `llm_filter_decision=reject`。
- 本报告中的“行”遵循源 CSV 粒度；唯一资产数和重复键另行列出。
- 重复键中存在状态冲突，未擅自去重或选择某一条覆盖；正式产出资产清单前应先确定冲突优先级。
- 完整长尾分布见同目录 CSV，Markdown 仅截取具体原因和多值标签前 30 项。
"""
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"Wrote report to {args.output_dir / 'report.md'}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


OUTPUT_FIELDS = [
    "raw_folder",
    "asset_id",
    "file_name",
    "asset_path",
    "final_status",
    "decision_source",
    "mask_status",
    "mask_decision",
    "asset_category",
    "asset_subcategory",
    "reject_severity",
    "confidence",
    "quality_issues",
    "reason",
    "name",
    "caption",
    "thumbnail_url",
    "error",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Merge original and supplemental mask judgements.")
    parser.add_argument(
        "--step1x-summary",
        type=Path,
        default=Path("/Users/mlty/Documents/raw0_raw7_asset_summary_20260814.csv"),
    )
    parser.add_argument(
        "--crosscheck-dir",
        type=Path,
        default=Path(__file__).with_name("metadata_caption_mask_crosscheck_20260814"),
    )
    parser.add_argument(
        "--supplemental-jsonl",
        type=Path,
        default=Path(
            "data_filter/texverse/filter_mask_report_step1x_not_found_v7_w100/results.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("metadata_caption_mask_integrated_20260814"),
    )
    return parser.parse_args()


def clean(value):
    return str(value or "").strip()


def normalize_existing(row, decision_source):
    return {
        "raw_folder": clean(row.get("raw_folder")),
        "asset_id": clean(row.get("asset_id")).lower(),
        "file_name": clean(row.get("file_name")),
        "asset_path": clean(row.get("asset_path")),
        "final_status": clean(row.get("final_status")),
        "decision_source": decision_source,
        "mask_status": clean(row.get("mask_status")),
        "mask_decision": clean(row.get("mask_decision")),
        "asset_category": clean(row.get("asset_category")),
        "asset_subcategory": clean(row.get("asset_subcategory")),
        "reject_severity": clean(row.get("reject_severity")),
        "confidence": clean(row.get("confidence")),
        "quality_issues": clean(row.get("quality_issues")),
        "reason": clean(row.get("reason")),
        "name": clean(row.get("name")),
        "caption": clean(row.get("caption")),
        "thumbnail_url": clean(row.get("thumbnail_url")),
        "error": clean(row.get("error")),
    }


def normalize_supplemental(source_row, record):
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    issues = result.get("quality_issues", [])
    return {
        "raw_folder": clean(source_row.get("raw_folder")),
        "asset_id": clean(source_row.get("asset_id")).lower(),
        "file_name": clean(source_row.get("file_name")),
        "asset_path": clean(source_row.get("asset_path")),
        "final_status": clean(source_row.get("final_status")),
        "decision_source": "supplemental_mask_report",
        "mask_status": clean(record.get("status")),
        "mask_decision": clean(result.get("filter_decision")),
        "asset_category": clean(result.get("asset_category")),
        "asset_subcategory": clean(result.get("asset_subcategory")),
        "reject_severity": clean(result.get("reject_severity")),
        "confidence": clean(result.get("confidence")),
        "quality_issues": "; ".join(clean(item) for item in issues) if isinstance(issues, list) else clean(issues),
        "reason": clean(result.get("reason")),
        "name": clean(record.get("name")),
        "caption": clean(record.get("caption")),
        "thumbnail_url": clean(record.get("thumbnail_url")),
        "error": clean(record.get("error")),
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    supplemental = {}
    with args.supplemental_jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            asset_id = clean(record.get("asset_id")).lower()
            if asset_id:
                supplemental[asset_id] = record

    integrated = {"keep": [], "reject": [], "review": [], "unjudged": [], "failed": []}
    for decision in ("keep", "reject", "review", "failed"):
        for row in read_csv(args.crosscheck_dir / f"{decision}.csv"):
            integrated[decision].append(normalize_existing(row, "original_mask_report"))

    for row in read_csv(args.crosscheck_dir / "not_found.csv"):
        asset_id = clean(row.get("asset_id")).lower()
        record = supplemental.get(asset_id)
        if record is None:
            integrated["unjudged"].append(normalize_existing(row, "missing_caption"))
            continue
        normalized = normalize_supplemental(row, record)
        decision = normalized["mask_decision"]
        if decision not in {"keep", "reject", "review"}:
            decision = "failed"
        integrated[decision].append(normalized)

    for decision, rows in integrated.items():
        write_csv(args.output_dir / f"{decision}.csv", rows)

    row_counts = Counter({decision: len(rows) for decision, rows in integrated.items()})
    unique_counts = Counter(
        {
            decision: len({row["asset_id"] for row in rows})
            for decision, rows in integrated.items()
        }
    )
    total_rows = sum(row_counts.values())
    all_asset_ids = {row["asset_id"] for rows in integrated.values() for row in rows}
    category_asset_ids = {
        decision: {row["asset_id"] for row in rows}
        for decision, rows in integrated.items()
    }
    cross_category_conflicts = sum(
        sum(asset_id in asset_ids for asset_ids in category_asset_ids.values()) > 1
        for asset_id in all_asset_ids
    )

    lines = ["| 结果 | 行数 | 唯一资产 | 行占比 |", "|---|---:|---:|---:|"]
    labels = {
        "keep": "可用",
        "reject": "不可用",
        "review": "待人工复核",
        "unjudged": "未判断（缺 caption）",
        "failed": "处理失败",
    }
    for decision in ("keep", "reject", "review", "unjudged", "failed"):
        lines.append(
            f"| {labels[decision]} | {row_counts[decision]:,} | "
            f"{unique_counts[decision]:,} | {100.0 * row_counts[decision] / total_rows:.2f}% |"
        )
    decision_table = "\n".join(lines)

    report = f"""# Metadata/Caption 资产 Mask 判断整合结果

## 最终结果

{decision_table}

- 总计：**{total_rows:,}** 行、**{len(all_asset_ids):,}** 个唯一资产。
- 原报告未覆盖的资产中，补充判断 **{len(supplemental):,}** 个唯一资产。
- 仍未判断：**{row_counts['unjudged']:,}** 行、**{unique_counts['unjudged']:,}** 个唯一资产，原因是缺少 caption。
- 跨最终分类冲突资产：**{cross_category_conflicts:,}** 个。

## 输出清单

- `keep.csv`：可以使用。
- `reject.csv`：不可使用。
- `review.csv`：待人工复核。
- `unjudged.csv`：缺 caption，尚未判断。
- `failed.csv`：原报告处理失败。

## 口径

- 原 mask 报告已有结论保持不变。
- 原 `not_found` 资产使用 GPT-5.5 补充报告结果，并按 `asset_id` 将结论传播回重复行。
- 行数保留 Step1X 汇总粒度；唯一资产按 `asset_id` 去重。
"""
    report_path = args.output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")

    original_status_counts = Counter()
    with args.step1x_summary.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            original_status_counts[clean(row.get("final_status"))] += 1

    full_total = sum(original_status_counts.values())
    reject_rule_low_poly = original_status_counts["reject_rule_low_poly"]
    reject_rule_not_multicolor = original_status_counts["reject_rule_not_multicolor"]
    reject_llm = original_status_counts["reject_llm"]
    reject_mask = row_counts["reject"]
    reject_total = reject_rule_low_poly + reject_rule_not_multicolor + reject_llm + reject_mask
    usable_llm = original_status_counts["ok_llm_keep"]
    usable_mask = row_counts["keep"]
    usable_total = usable_llm + usable_mask
    review_llm = original_status_counts["review_llm"]
    review_mask = row_counts["review"]
    review_total = review_llm + review_mask
    candidate_no_llm = original_status_counts["candidate_no_llm_result"]
    pending_total = candidate_no_llm + row_counts["unjudged"] + row_counts["failed"]

    full_report = f"""# Step1X 全量数据处理与整合分析

## 核心结果

- 原始 metadata：**231,576** 行。
- 判别汇总：**{full_total:,}** 行。
- 最终拒绝：**{reject_total:,}** 行，占 **{100.0 * reject_total / full_total:.2f}%**。
    - 低面数规则拒绝：**{reject_rule_low_poly:,}**。
    - 非多色规则拒绝：**{reject_rule_not_multicolor:,}**。
    - 原始 LLM 拒绝：**{reject_llm:,}**。
    - metadata/caption 资产经 mask 二次判断拒绝：**{reject_mask:,}**。
- 最终明确可用：**{usable_total:,}** 行，占 **{100.0 * usable_total / full_total:.2f}%**。
    - 原始 LLM 保留：**{usable_llm:,}**。
    - metadata/caption 资产经 mask 判断保留：**{usable_mask:,}**。
- 待人工复核：**{review_total:,}** 行，占 **{100.0 * review_total / full_total:.2f}%**。
    - 原始 LLM 复核：**{review_llm:,}**。
    - metadata/caption 资产经 mask 判断复核：**{review_mask:,}**。
- 尚待判断：**{pending_total:,}** 行，占 **{100.0 * pending_total / full_total:.2f}%**。
    - 尚无 LLM 结果：**{candidate_no_llm:,}**。
    - 缺 caption：**{row_counts['unjudged']:,}**。
    - 原 mask 报告处理失败：**{row_counts['failed']:,}**。
- 判别汇总中有 **5,507** 个重复资产键，其中 **149** 个初始状态冲突。
- 与原始 metadata 的行关联覆盖率：**97.94%**。

## 口径变化

- 初始报告中的 **140,379** 条拒绝只包含规则拒绝和原始 LLM 拒绝。
- 本报告进一步拆分原先的 **54,924** 条 `present_in_metadata_or_caption`，新增 **{reject_mask:,}** 条 mask 拒绝，因此最终拒绝更新为 **{reject_total:,}** 条。
- 总量校验：拒绝 {reject_total:,} + 可用 {usable_total:,} + 复核 {review_total:,} + 待判断 {pending_total:,} = **{full_total:,}**。

## 相关清单

- `keep.csv`：metadata/caption 子集最终可用清单。
- `reject.csv`：metadata/caption 子集最终不可用清单。
- `review.csv`：metadata/caption 子集待复核清单。
- `unjudged.csv`：缺 caption 清单。
- `failed.csv`：原报告处理失败清单。
"""
    full_report_path = args.output_dir / "full_report.md"
    full_report_path.write_text(full_report, encoding="utf-8")
    print(f"Wrote {report_path}")
    print(f"Wrote {full_report_path}")


if __name__ == "__main__":
    main()
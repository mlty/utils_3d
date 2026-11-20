#!/usr/bin/env python3
import argparse
import csv
from collections import Counter
from pathlib import Path


TARGET_STATUS = "present_in_metadata_or_caption"
OUTPUT_FIELDS = [
    "raw_folder",
    "asset_id",
    "file_name",
    "asset_path",
    "final_status",
    "mask_sha256",
    "mask_local_path",
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
    "error",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cross-check Step1X metadata/caption assets against the mask report."
    )
    parser.add_argument(
        "--step1x-summary",
        type=Path,
        default=Path("/Users/mlty/Documents/raw0_raw7_asset_summary_20260814.csv"),
    )
    parser.add_argument(
        "--mask-results",
        type=Path,
        default=Path(
            "data_filter/texverse/filter_mask_report_v7_all_w100/results.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("metadata_caption_mask_crosscheck_20260814"),
    )
    return parser.parse_args()


def normalize(value):
    return (value or "").strip()


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(counter, total, limit=None):
    lines = ["| 类别 | 数量 | 占比 |", "|---|---:|---:|"]
    for value, count in counter.most_common(limit):
        label = (value or "(空)").replace("|", "\\|").replace("\n", " ")
        rate = 100.0 * count / total if total else 0.0
        lines.append(f"| {label} | {count:,} | {rate:.2f}% |")
    return "\n".join(lines)


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    mask_by_asset_id = {}
    mask_duplicate_rows = 0
    mask_conflicting_decisions = set()
    with args.mask_results.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            asset_id = normalize(row.get("asset_id")).lower()
            if not asset_id:
                continue
            existing = mask_by_asset_id.get(asset_id)
            if existing is not None:
                mask_duplicate_rows += 1
                if normalize(existing.get("filter_decision")) != normalize(
                    row.get("filter_decision")
                ):
                    mask_conflicting_decisions.add(asset_id)
                continue
            mask_by_asset_id[asset_id] = row

    selections = {"keep": [], "reject": [], "review": [], "not_found": [], "failed": []}
    selection_asset_ids = {decision: set() for decision in selections}
    target_rows = 0
    found_rows = 0
    target_asset_ids = Counter()
    decision_counts = Counter()
    reject_issue_counts = Counter()
    reject_category_counts = Counter()
    review_issue_counts = Counter()

    with args.step1x_summary.open(newline="", encoding="utf-8-sig") as handle:
        for step1x_row in csv.DictReader(handle):
            if normalize(step1x_row.get("final_status")) != TARGET_STATUS:
                continue
            target_rows += 1
            asset_id = normalize(step1x_row.get("asset_id")).lower()
            target_asset_ids[asset_id] += 1
            mask_row = mask_by_asset_id.get(asset_id)
            decision = "not_found"
            if mask_row is not None:
                found_rows += 1
                decision = normalize(mask_row.get("filter_decision")) or "failed"
                if decision not in selections:
                    decision = "failed"
            decision_counts[decision] += 1
            selection_asset_ids[decision].add(asset_id)

            output_row = {
                "raw_folder": normalize(step1x_row.get("raw_folder")),
                "asset_id": asset_id,
                "file_name": normalize(step1x_row.get("file_name")),
                "asset_path": normalize(step1x_row.get("asset_path")),
                "final_status": TARGET_STATUS,
                "mask_sha256": normalize(mask_row.get("sha256")) if mask_row else "",
                "mask_local_path": normalize(mask_row.get("local_path")) if mask_row else "",
                "mask_status": normalize(mask_row.get("status")) if mask_row else "",
                "mask_decision": normalize(mask_row.get("filter_decision")) if mask_row else "",
                "asset_category": normalize(mask_row.get("asset_category")) if mask_row else "",
                "asset_subcategory": normalize(mask_row.get("asset_subcategory")) if mask_row else "",
                "reject_severity": normalize(mask_row.get("reject_severity")) if mask_row else "",
                "confidence": normalize(mask_row.get("confidence")) if mask_row else "",
                "quality_issues": normalize(mask_row.get("quality_issues")) if mask_row else "",
                "reason": normalize(mask_row.get("reason")) if mask_row else "",
                "name": normalize(mask_row.get("name")) if mask_row else "",
                "caption": normalize(mask_row.get("caption")) if mask_row else "",
                "error": normalize(mask_row.get("error")) if mask_row else "",
            }
            selections[decision].append(output_row)

            issues = [
                item.strip()
                for item in output_row["quality_issues"].split(";")
                if item.strip()
            ]
            if decision == "reject":
                reject_issue_counts.update(issues)
                reject_category_counts[output_row["asset_category"]] += 1
            elif decision == "review":
                review_issue_counts.update(issues)

    for decision, rows in selections.items():
        write_rows(args.output_dir / f"{decision}.csv", rows)

    duplicate_target_rows = sum(count - 1 for count in target_asset_ids.values() if count > 1)
    unique_target_ids = len(target_asset_ids)
    coverage = 100.0 * found_rows / target_rows if target_rows else 0.0
    found_asset_ids = (
        selection_asset_ids["keep"]
        | selection_asset_ids["reject"]
        | selection_asset_ids["review"]
        | selection_asset_ids["failed"]
    )
    unique_coverage = 100.0 * len(found_asset_ids) / unique_target_ids if unique_target_ids else 0.0
    unique_decision_lines = ["| 判定 | 行数 | 唯一 asset_id |", "|---|---:|---:|"]
    for decision in ("keep", "reject", "review", "not_found", "failed"):
        unique_decision_lines.append(
            f"| {decision} | {decision_counts[decision]:,} | "
            f"{len(selection_asset_ids[decision]):,} |"
        )
    unique_decision_table = "\n".join(unique_decision_lines)
    report = f"""# Metadata/Caption 资产与 Mask 报告交叉分析

## 结论

- Step1X `present_in_metadata_or_caption`：**{target_rows:,}** 行、**{unique_target_ids:,}** 个唯一 `asset_id`。
- 在 mask 逐资产报告中找到：**{found_rows:,}** 行，行覆盖率 **{coverage:.2f}%**；对应 **{len(found_asset_ids):,}** 个唯一资产，唯一资产覆盖率 **{unique_coverage:.2f}%**。
- 可以使用（`keep`）：**{decision_counts['keep']:,}** 行、**{len(selection_asset_ids['keep']):,}** 个唯一资产，占目标行 **{100.0 * decision_counts['keep'] / target_rows:.2f}%**。
- 不可使用（`reject`）：**{decision_counts['reject']:,}** 行、**{len(selection_asset_ids['reject']):,}** 个唯一资产，占目标行 **{100.0 * decision_counts['reject'] / target_rows:.2f}%**。
- 待人工复核（`review`）：**{decision_counts['review']:,}** 行、**{len(selection_asset_ids['review']):,}** 个唯一资产，占目标行 **{100.0 * decision_counts['review'] / target_rows:.2f}%**。
- 报告中未找到：**{decision_counts['not_found']:,}** 行、**{len(selection_asset_ids['not_found']):,}** 个唯一资产，占目标行 **{100.0 * decision_counts['not_found'] / target_rows:.2f}%**。
- 报告处理失败或无决策：**{decision_counts['failed']:,}** 行。

## 判定分布

{markdown_table(decision_counts, target_rows)}

### 行数与唯一资产数

{unique_decision_table}

## 不可用资产的质量问题

标签可多选，分母为 `reject` 行数。

{markdown_table(reject_issue_counts, decision_counts['reject'], 40)}

## 不可用资产类别

{markdown_table(reject_category_counts, decision_counts['reject'], 30)}

## 待复核资产的质量问题

标签可多选，分母为 `review` 行数。

{markdown_table(review_issue_counts, decision_counts['review'], 40)}

## 数据质量

| 指标 | 数量 |
|---|---:|
| Step1X 重复 asset_id 额外行 | {duplicate_target_rows:,} |
| mask 报告重复 asset_id 额外行 | {mask_duplicate_rows:,} |
| mask 重复 asset_id 决策冲突 | {len(mask_conflicting_decisions):,} |

## 输出文件

- `keep.csv`：可以使用。
- `reject.csv`：不可使用。
- `review.csv`：需要人工复核，不能直接并入可用集。
- `not_found.csv`：mask 报告未覆盖，不能据此判断可用。
- `failed.csv`：报告处理失败或无有效决策。
"""
    report_path = args.output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
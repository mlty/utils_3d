#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze metadata, caption, and thumbnail coverage for mask-report misses."
    )
    parser.add_argument(
        "--not-found",
        type=Path,
        default=Path(__file__).with_name("metadata_caption_mask_crosscheck_20260814")
        / "not_found.csv",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata.json"),
    )
    parser.add_argument(
        "--captions",
        type=Path,
        default=Path("/Users/mlty/Downloads/caption.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("not_found_source_analysis_20260814"),
    )
    return parser.parse_args()


def text(value):
    return value.strip() if isinstance(value, str) else ""


def availability_key(has_metadata, has_description, has_caption, has_thumbnail):
    return " | ".join(
        (
            f"metadata={'yes' if has_metadata else 'no'}",
            f"description={'yes' if has_description else 'no'}",
            f"caption={'yes' if has_caption else 'no'}",
            f"thumbnail={'yes' if has_thumbnail else 'no'}",
        )
    )


def markdown_table(counter, total):
    lines = ["| 类别 | 数量 | 占比 |", "|---|---:|---:|"]
    for value, count in counter.most_common():
        label = str(value or "(空)").replace("|", "\\|")
        rate = 100.0 * count / total if total else 0.0
        lines.append(f"| {label} | {count:,} | {rate:.2f}% |")
    return "\n".join(lines)


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with args.metadata.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    with args.captions.open(encoding="utf-8") as handle:
        captions = json.load(handle)

    with args.not_found.open(newline="", encoding="utf-8-sig") as handle:
        source_rows = list(csv.DictReader(handle))

    unique_rows = {}
    for row in source_rows:
        unique_rows.setdefault(text(row.get("asset_id")).lower(), row)

    row_combinations = Counter()
    unique_combinations = Counter()
    raw_folder_counts = Counter()
    extension_counts = Counter()
    metadata_field_counts = Counter()
    exact_png_url_field = 0
    eligible_rows = 0
    eligible_unique = 0
    output_rows = []

    for row in source_rows:
        asset_id = text(row.get("asset_id")).lower()
        item = metadata.get(asset_id)
        caption = text(captions.get(asset_id))
        has_metadata = isinstance(item, dict)
        description = text(item.get("description")) if has_metadata else ""
        thumbnail_url = text(item.get("thumbnail_url")) if has_metadata else ""
        has_description = bool(description)
        has_caption = bool(caption)
        has_thumbnail = bool(thumbnail_url)
        key = availability_key(has_metadata, has_description, has_caption, has_thumbnail)
        row_combinations[key] += 1
        raw_folder_counts[text(row.get("raw_folder"))] += 1
        eligible = has_metadata and has_caption and has_thumbnail
        eligible_rows += int(eligible)

        if has_metadata:
            for field, value in item.items():
                if value not in (None, "", [], {}):
                    metadata_field_counts[field] += 1
            exact_png_url_field += int(bool(text(item.get("png_url"))))
        if has_thumbnail:
            suffix = Path(urlparse(thumbnail_url).path).suffix.lower() or "no_extension"
            extension_counts[suffix] += 1

        output_rows.append(
            {
                "raw_folder": text(row.get("raw_folder")),
                "asset_id": asset_id,
                "file_name": text(row.get("file_name")),
                "asset_path": text(row.get("asset_path")),
                "has_metadata": has_metadata,
                "has_metadata_description": has_description,
                "has_caption": has_caption,
                "has_thumbnail_url": has_thumbnail,
                "eligible_for_mask_evaluation": eligible,
                "name": text(item.get("name")) if has_metadata else "",
                "metadata_description": description,
                "caption": caption,
                "thumbnail_url": thumbnail_url,
            }
        )

    for asset_id, row in unique_rows.items():
        item = metadata.get(asset_id)
        caption = text(captions.get(asset_id))
        has_metadata = isinstance(item, dict)
        has_description = bool(text(item.get("description"))) if has_metadata else False
        has_thumbnail = bool(text(item.get("thumbnail_url"))) if has_metadata else False
        has_caption = bool(caption)
        unique_combinations[
            availability_key(has_metadata, has_description, has_caption, has_thumbnail)
        ] += 1
        eligible_unique += int(has_metadata and has_caption and has_thumbnail)

    output_fields = [
        "raw_folder",
        "asset_id",
        "file_name",
        "asset_path",
        "has_metadata",
        "has_metadata_description",
        "has_caption",
        "has_thumbnail_url",
        "eligible_for_mask_evaluation",
        "name",
        "metadata_description",
        "caption",
        "thumbnail_url",
    ]
    with (args.output_dir / "assets_with_sources.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    total_rows = len(source_rows)
    total_unique = len(unique_rows)
    metadata_rows = sum(count for key, count in row_combinations.items() if "metadata=yes" in key)
    description_rows = sum(count for key, count in row_combinations.items() if "description=yes" in key)
    caption_rows = sum(count for key, count in row_combinations.items() if "caption=yes" in key)
    thumbnail_rows = sum(count for key, count in row_combinations.items() if "thumbnail=yes" in key)

    report = f"""# Mask 报告未覆盖资产的来源信息分析

## 总结

- 分析对象：**{total_rows:,}** 行、**{total_unique:,}** 个唯一 `asset_id`。
- 可在 `metadata.json` 找到：**{metadata_rows:,}** 行（{100.0 * metadata_rows / total_rows:.2f}%）。
- 有非空 metadata `description`：**{description_rows:,}** 行（{100.0 * description_rows / total_rows:.2f}%）。
- 有非空 caption：**{caption_rows:,}** 行（{100.0 * caption_rows / total_rows:.2f}%）。
- 有非空 `thumbnail_url`：**{thumbnail_rows:,}** 行（{100.0 * thumbnail_rows / total_rows:.2f}%）。
- 同时满足 metadata、caption、thumbnail URL，可进入 mask 评估：**{eligible_rows:,}** 行（{100.0 * eligible_rows / total_rows:.2f}%）、**{eligible_unique:,}** 个唯一资产。
- metadata 中存在非空 `png_url` 字段：**{exact_png_url_field:,}** 行。当前图片字段实际名为 `thumbnail_url`。

## 信息组合分布（行）

{markdown_table(row_combinations, total_rows)}

## 信息组合分布（唯一资产）

{markdown_table(unique_combinations, total_unique)}

## 图片 URL 后缀

{markdown_table(extension_counts, thumbnail_rows)}

## Raw 分区分布

{markdown_table(raw_folder_counts, total_rows)}

## Metadata 非空字段覆盖

分母为全部 {total_rows:,} 行；一个资产可包含多个字段。

{markdown_table(metadata_field_counts, total_rows)}

## 说明

- `thumbnail_url` 是否存在仅检查 JSON 字段非空，未对远程 URL 发起网络请求。
- `eligible_for_mask_evaluation=True` 但未出现在 mask 报告，说明不是 caption/metadata/图片 URL 缺失导致，需要检查 mask 报告使用的输入 CSV 覆盖范围。
- 行级完整内容见 `assets_with_sources.csv`。
"""
    report_path = args.output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
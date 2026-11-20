#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


ASSET_ID_PATTERN = re.compile(r"([0-9a-fA-F]{32})(?:_[0-9]+)?(?=[.]glb$)")


def parse_args():
    parser = argparse.ArgumentParser(description="Keep usable Step1X metadata rows.")
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata_step1x.csv"),
    )
    parser.add_argument(
        "--keep-csv",
        type=Path,
        default=Path(__file__).with_name("metadata_caption_mask_integrated_20260814")
        / "keep.csv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata_step1x_remove.csv"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    keep_ids = set()
    with args.keep_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            asset_id = (row.get("asset_id") or "").strip().lower()
            if asset_id:
                keep_ids.add(asset_id)

    kept_rows = 0
    with args.input_csv.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("input CSV has no header")
        with args.output_csv.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                match = ASSET_ID_PATTERN.search((row.get("local_path") or "").strip())
                if match and match.group(1).lower() in keep_ids:
                    writer.writerow(row)
                    kept_rows += 1

    if kept_rows != len(keep_ids):
        raise ValueError(f"expected {len(keep_ids)} rows, wrote {kept_rows}")
    print(f"Wrote {kept_rows} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
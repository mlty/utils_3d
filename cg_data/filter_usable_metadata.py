#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Keep explicitly usable CGDATA metadata rows.")
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata_cg.csv"),
    )
    parser.add_argument(
        "--llm-csv",
        type=Path,
        required=True,
        help="CSV containing full_asset_id and filter_decision",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("/Users/mlty/Downloads/metadata_cg_remove.csv"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    decisions_by_id = defaultdict(set)
    with args.llm_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"full_asset_id", "filter_decision"}.issubset(
            reader.fieldnames
        ):
            raise ValueError("LLM CSV is missing full_asset_id or filter_decision")
        for row in reader:
            asset_id = (row.get("full_asset_id") or "").strip().lower()
            decision = (row.get("filter_decision") or "").strip().lower()
            if asset_id and decision:
                decisions_by_id[asset_id].add(decision)

    keep_ids = {
        asset_id
        for asset_id, decisions in decisions_by_id.items()
        if decisions == {"keep"}
    }

    kept_rows = 0
    kept_ids = set()
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.input_csv.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "sha256" not in reader.fieldnames:
            raise ValueError("input CSV is missing sha256")
        with args.output_csv.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            for row in reader:
                asset_id = (row.get("sha256") or "").strip().lower()
                if asset_id in keep_ids:
                    writer.writerow(row)
                    kept_rows += 1
                    kept_ids.add(asset_id)

    missing_ids = keep_ids - kept_ids
    if missing_ids:
        raise ValueError(f"{len(missing_ids)} keep IDs were not found in input CSV")
    if kept_rows != len(keep_ids):
        raise ValueError(
            f"expected one row per keep ID ({len(keep_ids)}), wrote {kept_rows}"
        )
    print(f"Wrote {kept_rows} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
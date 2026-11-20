import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASETS = (
    Path.home() / "Downloads/objaverse_xl_github_url_480k.json",
    Path.home() / "Downloads/objaverse_320k.json",
    Path.home() / "Data/objaverse_texture_30k.json",
)


def describe_record(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return {
            "type": "object",
            "fields": {key: type(value).__name__ for key, value in record.items()},
        }
    return {"type": type(record).__name__}


def take_raw_records(data: Any, record_count: int) -> Any:
    if isinstance(data, dict):
        return dict(list(data.items())[:record_count])
    if isinstance(data, list):
        return data[:record_count]
    raise TypeError(f"Unsupported JSON root type: {type(data).__name__}")


def analyze_dataset(
    source: Path,
    output_dir: Path,
    record_count: int,
) -> dict[str, Any]:
    with source.open(encoding="utf-8") as file:
        data = json.load(file)

    raw_records = take_raw_records(data, record_count)
    raw_path = output_dir / f"{source.stem}.raw{record_count}.json"
    raw_path.write_text(
        json.dumps(raw_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    first_record = next(iter(data.items())) if isinstance(data, dict) else data[0]
    return {
        "source": str(source),
        "root_type": "object" if isinstance(data, dict) else "array",
        "total_records": len(data),
        "raw_records": len(raw_records),
        "raw_file": str(raw_path),
        "record_structure": (
            {"key": type(first_record[0]).__name__, "value": type(first_record[1]).__name__}
            if isinstance(data, dict)
            else describe_record(first_record)
        ),
    }


def analyze_relationship(first_source: Path, second_source: Path) -> dict[str, Any]:
    with first_source.open(encoding="utf-8") as file:
        first_data = json.load(file)
    with second_source.open(encoding="utf-8") as file:
        second_data = json.load(file)

    first_unique = set(first_data)
    second_unique = set(second_data)
    intersection = first_unique & second_unique
    return {
        "first_dataset": first_source.name,
        "second_dataset": second_source.name,
        "first_unique_records": len(first_unique),
        "second_unique_records": len(second_unique),
        "intersection_records": len(intersection),
        "second_only_records": len(second_unique - first_unique),
        "second_is_subset_of_first": second_unique <= first_unique,
        "intersection_percent_of_first": round(
            len(intersection) / len(first_unique) * 100, 4
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export leading raw records and summarize Step1X JSON datasets."
    )
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    if args.sample_size < 1:
        parser.error("--sample-size must be at least 1")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries = [
        analyze_dataset(source, args.out_dir, args.sample_size)
        for source in DEFAULT_DATASETS
    ]
    summary = {
        "datasets": summaries,
        "relationships": [analyze_relationship(DEFAULT_DATASETS[1], DEFAULT_DATASETS[2])],
    }
    summary_path = args.out_dir / "dataset_samples_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
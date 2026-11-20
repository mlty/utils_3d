import gc
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).parent
METADATA_PATH = Path.home() / "Downloads/metadata.json"
CAPTION_PATH = Path.home() / "Downloads/caption.json"
RAW_PATHS = (
    ROOT / "objaverse_320k.raw100.json",
    ROOT / "objaverse_texture_30k.raw100.json",
    ROOT / "objaverse_xl_github_url_480k.raw100.json",
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def build_records(path: Path) -> list[dict[str, Any]]:
    raw_data = load_json(path)
    if isinstance(raw_data, list):
        return [
            {
                "relative_path": relative_path,
                "lookup_ids": [Path(relative_path).stem],
            }
            for relative_path in raw_data
        ]

    records = []
    for sha256, url in raw_data.items():
        url_stem = Path(unquote(urlparse(url).path)).stem
        records.append(
            {
                "sha256": sha256,
                "url": url,
                "lookup_ids": list(dict.fromkeys((sha256, url_stem))),
            }
        )
    return records


def attach_matches(
    datasets: dict[str, list[dict[str, Any]]],
    lookup_data: dict[str, Any],
    output_field: str,
) -> None:
    for records in datasets.values():
        for record in records:
            matched_id = next(
                (asset_id for asset_id in record["lookup_ids"] if asset_id in lookup_data),
                None,
            )
            record[f"{output_field}_matched_id"] = matched_id
            record[output_field] = lookup_data.get(matched_id) if matched_id else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    metadata_matches = sum(record["metadata"] is not None for record in records)
    caption_matches = sum(record["caption"] is not None for record in records)
    metadata_descriptions = sum(
        bool(record["metadata"].get("description"))
        for record in records
        if record["metadata"] is not None
    )
    return {
        "total_records": len(records),
        "metadata_matches": metadata_matches,
        "metadata_match_rate": metadata_matches / len(records),
        "metadata_nonempty_descriptions": metadata_descriptions,
        "caption_matches": caption_matches,
        "caption_match_rate": caption_matches / len(records),
    }


def main() -> None:
    datasets = {path.name: build_records(path) for path in RAW_PATHS}

    metadata = load_json(METADATA_PATH)
    attach_matches(datasets, metadata, "metadata")
    del metadata
    gc.collect()

    captions = load_json(CAPTION_PATH)
    attach_matches(datasets, captions, "caption")
    del captions
    gc.collect()

    result = {
        "lookup": {
            "metadata": str(METADATA_PATH),
            "caption": str(CAPTION_PATH),
            "objaverse_lookup_key": "relative path filename stem",
            "github_lookup_keys": ["SHA-256 object key", "URL filename stem"],
        },
        "summary": {
            dataset_name: summarize(records)
            for dataset_name, records in datasets.items()
        },
        "records": datasets,
    }
    output_path = ROOT / "description_matches_raw100.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
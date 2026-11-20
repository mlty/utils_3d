import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
CSV_PATH = Path.home() / "Downloads/metadata (2).csv"
GITHUB_PATH = Path.home() / "Downloads/objaverse_xl_github_url_480k.json"
OBJAVERSE_PATH = Path.home() / "Downloads/objaverse_320k.json"
TEXTURE_PATH = Path.home() / "Data/objaverse_texture_30k.json"


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def normalize_objaverse_path(local_path: str) -> str:
    return Path(local_path).name.replace("_", "/", 1)


def source_label(in_github: bool, in_objaverse: bool, in_texture: bool) -> str:
    sources = []
    if in_github:
        sources.append("github_480k")
    if in_objaverse:
        sources.append("objaverse_320k")
    if in_texture:
        sources.append("texture_30k")
    return "+".join(sources) if sources else "unmatched"


def main() -> None:
    github_sha256 = set(load_json(GITHUB_PATH))
    objaverse_paths = set(load_json(OBJAVERSE_PATH))
    texture_paths = set(load_json(TEXTURE_PATH))

    independent_counts = Counter()
    combination_counts = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen_sha256: set[str] = set()
    seen_local_paths: set[str] = set()
    duplicate_sha256_rows = 0
    duplicate_local_path_rows = 0

    output_path = ROOT / "metadata_2_source_membership.csv"
    with CSV_PATH.open(newline="", encoding="utf-8-sig") as source_file, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as output_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {CSV_PATH}")
        extra_fields = [
            "normalized_objaverse_path",
            "in_github_480k",
            "in_objaverse_320k",
            "in_texture_30k",
            "matched_sources",
        ]
        writer = csv.DictWriter(output_file, fieldnames=reader.fieldnames + extra_fields)
        writer.writeheader()

        total_rows = 0
        for row in reader:
            total_rows += 1
            sha256 = row["sha256"].strip()
            local_path = row["local_path"].strip()
            normalized_path = normalize_objaverse_path(local_path)
            in_github = sha256 in github_sha256
            in_objaverse = normalized_path in objaverse_paths
            in_texture = normalized_path in texture_paths
            label = source_label(in_github, in_objaverse, in_texture)

            independent_counts["github_480k"] += in_github
            independent_counts["objaverse_320k"] += in_objaverse
            independent_counts["texture_30k"] += in_texture
            independent_counts["matched_any"] += in_github or in_objaverse or in_texture
            combination_counts[label] += 1

            duplicate_sha256_rows += sha256 in seen_sha256
            duplicate_local_path_rows += local_path in seen_local_paths
            seen_sha256.add(sha256)
            seen_local_paths.add(local_path)

            if len(examples[label]) < 5:
                examples[label].append(
                    {
                        "sha256": sha256,
                        "local_path": local_path,
                        "normalized_objaverse_path": normalized_path,
                    }
                )

            writer.writerow(
                row
                | {
                    "normalized_objaverse_path": normalized_path,
                    "in_github_480k": in_github,
                    "in_objaverse_320k": in_objaverse,
                    "in_texture_30k": in_texture,
                    "matched_sources": label,
                }
            )

    summary = {
        "input": str(CSV_PATH),
        "total_rows": total_rows,
        "matching_rules": {
            "github_480k": "CSV sha256 exactly matches JSON object key",
            "objaverse_320k": (
                "local_path basename first underscore is converted to slash, then exact path match"
            ),
            "texture_30k": (
                "local_path basename first underscore is converted to slash, then exact path match"
            ),
        },
        "independent_matches": dict(independent_counts),
        "independent_match_rates": {
            key: round(value / total_rows, 6)
            for key, value in independent_counts.items()
        },
        "reference_coverage": {
            "github_480k": {
                "reference_records": len(github_sha256),
                "matched_csv_rows": independent_counts["github_480k"],
                "coverage_rate": round(
                    independent_counts["github_480k"] / len(github_sha256), 6
                ),
            },
            "objaverse_320k": {
                "reference_records": len(objaverse_paths),
                "matched_csv_rows": independent_counts["objaverse_320k"],
                "coverage_rate": round(
                    independent_counts["objaverse_320k"] / len(objaverse_paths), 6
                ),
            },
            "texture_30k": {
                "reference_records": len(texture_paths),
                "matched_csv_rows": independent_counts["texture_30k"],
                "coverage_rate": round(
                    independent_counts["texture_30k"] / len(texture_paths), 6
                ),
            },
        },
        "exclusive_combinations": dict(sorted(combination_counts.items())),
        "duplicates": {
            "duplicate_sha256_rows": duplicate_sha256_rows,
            "duplicate_local_path_rows": duplicate_local_path_rows,
            "unique_sha256": len(seen_sha256),
            "unique_local_paths": len(seen_local_paths),
        },
        "reference_relationships": {
            "texture_is_subset_of_objaverse": texture_paths <= objaverse_paths,
            "texture_paths_outside_objaverse": len(texture_paths - objaverse_paths),
        },
        "examples_by_combination": examples,
        "annotated_csv": str(output_path),
    }
    summary_path = ROOT / "metadata_2_source_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "examples_by_combination"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
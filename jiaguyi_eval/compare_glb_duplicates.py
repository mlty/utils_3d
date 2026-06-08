#!/usr/bin/env python3
"""Find exact duplicate GLB/glTF files across two datasets.

The comparison is byte-exact: two assets are considered duplicate only when the
full SHA-256 hash of the model file is identical. To avoid reading every large
file fully, the script first narrows candidates by file size and sampled quick
hash, then computes full SHA-256 only for cross-dataset candidates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_EXTENSIONS = (".glb", ".gltf")


@dataclass
class FileRecord:
    dataset: str
    root: Path
    path: Path
    relative_path: str
    extension: str
    size_bytes: int
    mtime_ns: int
    quick_hash: str = ""
    sha256: str = ""
    error: str = ""


def normalize_extensions(value: str) -> Tuple[str, ...]:
    extensions = []
    for item in value.split(","):
        item = item.strip().lower()
        if not item:
            continue
        extensions.append(item if item.startswith(".") else f".{item}")
    return tuple(dict.fromkeys(extensions))


def scan_files(root: Path, dataset: str, extensions: Sequence[str]) -> List[FileRecord]:
    records: List[FileRecord] = []
    extension_set = {item.lower() for item in extensions}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extension_set:
            continue
        try:
            stat = path.stat()
            relative_path = path.relative_to(root).as_posix()
            records.append(
                FileRecord(
                    dataset=dataset,
                    root=root,
                    path=path,
                    relative_path=relative_path,
                    extension=path.suffix.lower(),
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
            )
        except OSError as exc:
            records.append(
                FileRecord(
                    dataset=dataset,
                    root=root,
                    path=path,
                    relative_path=str(path),
                    extension=path.suffix.lower(),
                    size_bytes=-1,
                    mtime_ns=0,
                    error=str(exc),
                )
            )
    return records


def quick_hash_file(path: Path, size_bytes: int, sample_bytes: int) -> str:
    digest = hashlib.sha256()
    digest.update(str(size_bytes).encode("ascii"))
    if size_bytes <= 0:
        return digest.hexdigest()
    if size_bytes <= sample_bytes * 3:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    offsets = (0, max(0, size_bytes // 2 - sample_bytes // 2), max(0, size_bytes - sample_bytes))
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            digest.update(offset.to_bytes(8, "little", signed=False))
            digest.update(handle.read(sample_bytes))
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_hash_jobs(
    records: Iterable[FileRecord],
    hash_kind: str,
    workers: int,
    sample_bytes: int,
    progress_every: int,
) -> None:
    record_list = list(records)
    if not record_list:
        return

    def compute(record: FileRecord) -> Tuple[FileRecord, str, str]:
        try:
            if hash_kind == "quick":
                return record, quick_hash_file(record.path, record.size_bytes, sample_bytes), ""
            return record, sha256_file(record.path), ""
        except OSError as exc:
            return record, "", str(exc)

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(compute, record) for record in record_list]
        for future in as_completed(futures):
            record, hash_value, error = future.result()
            if hash_kind == "quick":
                record.quick_hash = hash_value
            else:
                record.sha256 = hash_value
            if error:
                record.error = error
            completed += 1
            if progress_every > 0 and completed % progress_every == 0:
                print(f"{hash_kind} hash progress: {completed}/{len(record_list)}")


def group_records(records: Iterable[FileRecord], key_name: str) -> Dict[object, List[FileRecord]]:
    grouped: Dict[object, List[FileRecord]] = defaultdict(list)
    for record in records:
        grouped[getattr(record, key_name)].append(record)
    return grouped


def cross_dataset_keys(grouped: Dict[object, List[FileRecord]], left_name: str, right_name: str) -> set:
    keys = set()
    for key, records in grouped.items():
        datasets = {record.dataset for record in records}
        if left_name in datasets and right_name in datasets:
            keys.add(key)
    return keys


def write_manifest(path: Path, records: Sequence[FileRecord]) -> None:
    fieldnames = [
        "dataset",
        "path",
        "relative_path",
        "extension",
        "size_bytes",
        "mtime_ns",
        "quick_hash",
        "sha256",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "dataset": record.dataset,
                    "path": str(record.path),
                    "relative_path": record.relative_path,
                    "extension": record.extension,
                    "size_bytes": record.size_bytes,
                    "mtime_ns": record.mtime_ns,
                    "quick_hash": record.quick_hash,
                    "sha256": record.sha256,
                    "error": record.error,
                }
            )


def write_paths(path: Path, records: Sequence[FileRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in sorted(records, key=lambda item: item.relative_path):
            handle.write(str(record.path) + "\n")


def write_duplicate_reports(
    out_dir: Path,
    duplicate_groups: Sequence[Tuple[str, int, List[FileRecord], List[FileRecord]]],
    left_name: str,
    right_name: str,
) -> Dict[str, object]:
    pair_rows = []
    group_rows = []
    duplicate_left = []
    duplicate_right = []

    for group_index, (sha256, size_bytes, left_records, right_records) in enumerate(duplicate_groups, start=1):
        duplicate_left.extend(left_records)
        duplicate_right.extend(right_records)
        group_rows.append(
            {
                "group_id": group_index,
                "sha256": sha256,
                "size_bytes": size_bytes,
                f"{left_name}_count": len(left_records),
                f"{right_name}_count": len(right_records),
                f"{left_name}_paths": json.dumps([str(record.path) for record in left_records], ensure_ascii=False),
                f"{right_name}_paths": json.dumps([str(record.path) for record in right_records], ensure_ascii=False),
            }
        )
        for left_record in left_records:
            for right_record in right_records:
                pair_rows.append(
                    {
                        "group_id": group_index,
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                        f"{left_name}_path": str(left_record.path),
                        f"{left_name}_relative_path": left_record.relative_path,
                        f"{right_name}_path": str(right_record.path),
                        f"{right_name}_relative_path": right_record.relative_path,
                    }
                )

    with (out_dir / "duplicate_groups.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "group_id",
            "sha256",
            "size_bytes",
            f"{left_name}_count",
            f"{right_name}_count",
            f"{left_name}_paths",
            f"{right_name}_paths",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(group_rows)

    with (out_dir / "duplicate_pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "group_id",
            "sha256",
            "size_bytes",
            f"{left_name}_path",
            f"{left_name}_relative_path",
            f"{right_name}_path",
            f"{right_name}_relative_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pair_rows)

    write_paths(out_dir / f"duplicate_{left_name}_paths.txt", duplicate_left)
    write_paths(out_dir / f"duplicate_{right_name}_paths.txt", duplicate_right)

    return {
        "duplicate_group_count": len(group_rows),
        "duplicate_pair_count": len(pair_rows),
        f"duplicate_{left_name}_file_count": len({str(record.path) for record in duplicate_left}),
        f"duplicate_{right_name}_file_count": len({str(record.path) for record in duplicate_right}),
    }


def render_summary(summary: Dict[str, object], out_dir: Path, left_name: str, right_name: str) -> None:
    lines = ["# Cross Dataset GLB Duplicate Report", ""]
    for key, value in summary.items():
        if key == "largest_duplicate_groups":
            continue
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Largest Duplicate Groups", ""])
    lines.append(f"| sha256 | size bytes | {left_name} count | {right_name} count |")
    lines.append("|---|---:|---:|---:|")
    for item in summary.get("largest_duplicate_groups", []):
        lines.append(
            f"| {item['sha256']} | {item['size_bytes']} | {item[f'{left_name}_count']} | {item[f'{right_name}_count']} |"
        )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `duplicate_groups.csv`: one row per exact SHA-256 duplicate group.",
            "- `duplicate_pairs.csv`: all cross-dataset duplicate path pairs.",
            f"- `duplicate_{left_name}_paths.txt`: {left_name} files duplicated in {right_name}.",
            f"- `duplicate_{right_name}_paths.txt`: {right_name} files duplicated in {left_name}.",
            "- `manifest.csv`: scanned files with size and computed hashes.",
            "",
        ]
    )
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def compare(args: argparse.Namespace) -> Dict[str, object]:
    start_time = time.time()
    left_root = Path(args.left_dir).expanduser().resolve()
    right_root = Path(args.right_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    extensions = normalize_extensions(args.extensions)
    left_name = args.left_name or left_root.name
    right_name = args.right_name or right_root.name

    left_records = scan_files(left_root, left_name, extensions)
    right_records = scan_files(right_root, right_name, extensions)
    all_records = left_records + right_records

    size_groups = group_records([record for record in all_records if record.size_bytes >= 0], "size_bytes")
    cross_sizes = cross_dataset_keys(size_groups, left_name, right_name)
    quick_candidates = [record for record in all_records if record.size_bytes in cross_sizes and not record.error]
    print(f"scanned: {left_name}={len(left_records)}, {right_name}={len(right_records)}")
    print(f"cross-size candidate files: {len(quick_candidates)}")
    run_hash_jobs(quick_candidates, "quick", args.workers, args.quick_sample_bytes, args.progress_every)

    quick_groups = defaultdict(list)
    for record in quick_candidates:
        if record.quick_hash:
            quick_groups[(record.size_bytes, record.quick_hash)].append(record)
    cross_quick_keys = set()
    for key, records in quick_groups.items():
        datasets = {record.dataset for record in records}
        if left_name in datasets and right_name in datasets:
            cross_quick_keys.add(key)
    full_candidates = [record for key in cross_quick_keys for record in quick_groups[key]]
    print(f"cross-quick-hash candidate files: {len(full_candidates)}")
    run_hash_jobs(full_candidates, "sha256", args.workers, args.quick_sample_bytes, args.progress_every)

    sha_groups = defaultdict(list)
    for record in full_candidates:
        if record.sha256:
            sha_groups[(record.sha256, record.size_bytes)].append(record)

    duplicate_groups = []
    for (sha256, size_bytes), records in sha_groups.items():
        left_group = sorted([record for record in records if record.dataset == left_name], key=lambda item: item.relative_path)
        right_group = sorted([record for record in records if record.dataset == right_name], key=lambda item: item.relative_path)
        if left_group and right_group:
            duplicate_groups.append((sha256, size_bytes, left_group, right_group))
    duplicate_groups.sort(key=lambda item: (-item[1], item[0]))

    report_counts = write_duplicate_reports(out_dir, duplicate_groups, left_name, right_name)
    write_manifest(out_dir / "manifest.csv", all_records)

    error_count = sum(1 for record in all_records if record.error)
    extension_counts = Counter(record.extension for record in all_records)
    largest_groups = []
    for sha256, size_bytes, left_group, right_group in duplicate_groups[:20]:
        largest_groups.append(
            {
                "sha256": sha256,
                "size_bytes": size_bytes,
                f"{left_name}_count": len(left_group),
                f"{right_name}_count": len(right_group),
            }
        )
    summary: Dict[str, object] = {
        "left_name": left_name,
        "left_dir": str(left_root),
        "right_name": right_name,
        "right_dir": str(right_root),
        "extensions": list(extensions),
        f"{left_name}_file_count": len(left_records),
        f"{right_name}_file_count": len(right_records),
        "total_file_count": len(all_records),
        "cross_size_candidate_file_count": len(quick_candidates),
        "cross_quick_hash_candidate_file_count": len(full_candidates),
        "error_count": error_count,
        "extension_counts": dict(sorted(extension_counts.items())),
        **report_counts,
        "elapsed_sec": round(time.time() - start_time, 3),
        "largest_duplicate_groups": largest_groups,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_summary(summary, out_dir, left_name, right_name)
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-dir", required=True, help="First dataset directory")
    parser.add_argument("--right-dir", required=True, help="Second dataset directory")
    parser.add_argument("--left-name", default="", help="Label for the first dataset, default is directory name")
    parser.add_argument("--right-name", default="", help="Label for the second dataset, default is directory name")
    parser.add_argument("--out-dir", required=True, help="Output report directory")
    parser.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS), help="Comma-separated extensions to compare")
    parser.add_argument("--workers", type=int, default=8, help="Thread count for file hashing")
    parser.add_argument("--quick-sample-bytes", type=int, default=1024 * 1024, help="Bytes sampled at head/middle/tail for quick hash")
    parser.add_argument("--progress-every", type=int, default=500, help="Print hash progress every N files; 0 disables progress")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    summary = compare(args)
    print("===== cross dataset duplicate report =====")
    for key, value in summary.items():
        if key != "largest_duplicate_groups":
            print(f"{key}: {value}")
    print(f"report_dir: {Path(args.out_dir).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
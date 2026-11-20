#!/usr/bin/env python3
"""Sample reject reasons by category and download grouped thumbnails."""

from __future__ import annotations

import argparse
import csv
import html
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from download_report_images import download_image, write_gallery


CATEGORIES: List[Tuple[str, str]] = [
	("scanned_asset", "is_scanned_asset"),
	("large_floor_plane", "large_floor_plane"),
	("broken_or_damaged", "broken_or_damaged"),
	("rock_or_stone", "is_rock_or_stone"),
	("debris_or_fragment", "debris_or_fragment"),
	("unrecognizable_object", "unrecognizable_object"),
	("rough_sculpture", "rough_sculpture"),
	("ai_generated_asset", "is_ai_generated_asset"),
	("abnormal_proportions", "abnormal_proportions"),
	("battle_damaged", "battle_damaged"),
]


def reservoir_samples(csv_path: Path, sample_size: int, seed: int) -> tuple[List[str], Dict[str, List[Dict[str, str]]], Dict[str, int]]:
	rngs = {name: random.Random(f"{seed}:{name}") for name, _ in CATEGORIES}
	samples: Dict[str, List[Dict[str, str]]] = {name: [] for name, _ in CATEGORIES}
	counts = {name: 0 for name, _ in CATEGORIES}
	with csv_path.open(encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		fieldnames = list(reader.fieldnames or [])
		for row in reader:
			for name, field in CATEGORIES:
				if row.get(field) != "yes":
					continue
				counts[name] += 1
				bucket = samples[name]
				if len(bucket) < sample_size:
					bucket.append(dict(row))
				else:
					index = rngs[name].randrange(counts[name])
					if index < sample_size:
						bucket[index] = dict(row)
	return fieldnames, samples, counts


def write_samples(out_dir: Path, fieldnames: List[str], samples: Dict[str, List[Dict[str, str]]]) -> None:
	for name, _ in CATEGORIES:
		category_dir = out_dir / name
		category_dir.mkdir(parents=True, exist_ok=True)
		with (category_dir / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
			writer = csv.DictWriter(handle, fieldnames=fieldnames)
			writer.writeheader()
			writer.writerows(samples[name])


def download_samples(
	out_dir: Path,
	samples: Dict[str, List[Dict[str, str]]],
	workers: int,
	timeout_sec: int,
	retries: int,
) -> Dict[str, Dict[str, Dict[str, str]]]:
	results: Dict[str, Dict[str, Dict[str, str]]] = {name: {} for name, _ in CATEGORIES}
	with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
		futures = {}
		for name, _ in CATEGORIES:
			category_dir = out_dir / name
			for index, row in enumerate(samples[name], 1):
				future = executor.submit(download_image, index, row, category_dir, timeout_sec, retries)
				futures[future] = name
		for future in as_completed(futures):
			name = futures[future]
			result = future.result()
			results[name][result["asset_id"]] = result
	return results


def write_outputs(
	out_dir: Path,
	samples: Dict[str, List[Dict[str, str]]],
	candidate_counts: Dict[str, int],
	downloads: Dict[str, Dict[str, Dict[str, str]]],
) -> int:
	sections: List[str] = []
	total_failures = 0
	with (out_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=["category", "candidate_count", "sample_count", "downloaded", "failed"])
		writer.writeheader()
		for name, _ in CATEGORIES:
			category_dir = out_dir / name
			write_gallery(samples[name], downloads[name], category_dir)
			failures = sum(result["status"] != "ok" for result in downloads[name].values())
			downloaded = len(samples[name]) - failures
			total_failures += failures
			writer.writerow({
				"category": name,
				"candidate_count": candidate_counts[name],
				"sample_count": len(samples[name]),
				"downloaded": downloaded,
				"failed": failures,
			})
			sections.append(
				f'<li><a href="{html.escape(name)}/index.html">{html.escape(name)}</a> '
				f'({downloaded}/{len(samples[name])} images; {candidate_counts[name]} candidates)</li>'
			)
	page = (
		'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
		'<meta name="viewport" content="width=device-width,initial-scale=1">'
		'<title>Reject Category Samples</title></head><body>'
		'<h1>Reject Category Samples</h1><ul>' + "".join(sections) + '</ul></body></html>'
	)
	(out_dir / "index.html").write_text(page, encoding="utf-8")
	return total_failures


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("reject_csv", type=Path)
	parser.add_argument("--out-dir", type=Path, required=True)
	parser.add_argument("--sample-size", type=int, default=20)
	parser.add_argument("--seed", type=int, default=20260811)
	parser.add_argument("--workers", type=int, default=32)
	parser.add_argument("--timeout-sec", type=int, default=60)
	parser.add_argument("--retries", type=int, default=2)
	return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
	args = parse_args(argv)
	args.out_dir.mkdir(parents=True, exist_ok=True)
	fieldnames, samples, counts = reservoir_samples(args.reject_csv, args.sample_size, args.seed)
	write_samples(args.out_dir, fieldnames, samples)
	downloads = download_samples(args.out_dir, samples, args.workers, args.timeout_sec, args.retries)
	failures = write_outputs(args.out_dir, samples, counts, downloads)
	total = sum(len(rows) for rows in samples.values())
	print(f"categories={len(CATEGORIES)} samples={total} failures={failures} output={args.out_dir}")
	return 1 if failures else 0


if __name__ == "__main__":
	raise SystemExit(main())

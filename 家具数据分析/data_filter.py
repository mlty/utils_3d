#!/usr/bin/env python3
"""Find furniture/home assets in the removed metadata CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_INPUTS = (
	Path("/Users/mlty/Downloads/metadata_github_remove.csv"),
	Path("/Users/mlty/Downloads/metadata_sket_remove.csv"),
	Path("/Users/mlty/Downloads/metadata_tex_remove.csv"),
)
DEFAULT_METADATA_INPUTS = (
	Path("/Users/mlty/Downloads/ObjaverseXL_sketchfab.csv"),
	Path("/Users/mlty/Downloads/ObjaverseXL_github.csv"),
	Path("/Users/mlty/Downloads/metadata_github.csv"),
)
DEFAULT_OUT_DIR = Path(__file__).with_name("furniture_analysis_report")

TEXT_FIELDS = ("captions", "file_identifier", "local_path")
OUTPUT_FIELDS = (
	"source_file",
	"source_row",
	"sha256",
	"decision",
	"matched_groups",
	"matched_terms",
	"metadata_source",
	"aesthetic_score",
	"file_identifier",
	"local_path",
	"evidence",
)

FURNITURE_PATTERNS: dict[str, tuple[str, ...]] = {
	"furniture": (
		r"\b(furniture|furnishing|chair|armchair|stool|bench|sofa|couch|loveseat|ottoman|table|desk|bed|mattress|crib|cabinet|cupboard|wardrobe|closet|dresser|nightstand|bookshelf|bookcase|shelf|sideboard|drawer|vanity|console table|coffee table|dining table|tv stand)\b",
		r"家具|家居|椅子|扶手椅|凳子|长凳|沙发|桌子|书桌|床|床垫|婴儿床|柜|橱柜|衣柜|书架|架子|抽屉|梳妆台|茶几|餐桌|电视柜",
	),
	"lighting": (
		r"\b(lamp|lampshade|chandelier|sconce|pendant light|ceiling light|floor light|table light|wall light)\b",
		r"灯|台灯|吊灯|壁灯|落地灯|灯罩",
	),
	"home_appliance_fixture": (
		r"\b(appliance|refrigerator|fridge|freezer|oven|microwave|stove|cooktop|dishwasher|washing machine|dryer|sink|bathtub|toilet|shower|faucet|radiator|fireplace)\b",
		r"家电|冰箱|烤箱|微波炉|炉灶|洗碗机|洗衣机|烘干机|水槽|浴缸|马桶|淋浴|水龙头|暖气片|壁炉",
	),
	"soft_furnishing": (
		r"\b(rug|carpet|curtain|blind|pillow|cushion|blanket|quilt|duvet)\b",
		r"地毯|窗帘|百叶窗|枕头|靠垫|毯子|被子",
	),
}
EXCLUDE_IF_ONLY_PATTERNS = (
	re.compile(r"\b(tableware|plate|bowl|cup|glass|bottle|food|fruit|vegetable)\b", re.IGNORECASE),
)
VEHICLE_BED_PATTERN = re.compile(r"\b(pickup|truck|flatbed|vehicle|car)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Metadata:
	source: str
	file_identifier: str
	captions: str
	aesthetic_score: str


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--input", action="append", type=Path, dest="inputs", help="Removed metadata CSV to analyze. Can be repeated.")
	parser.add_argument("--metadata", action="append", type=Path, dest="metadata_inputs", help="Metadata CSV with sha256, captions, and file_identifier. Can be repeated.")
	parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
	parser.add_argument("--limit", type=int, default=0, help="Debug limit per input file. 0 means all rows.")
	return parser.parse_args()


def csv_rows(path: Path) -> Iterable[tuple[int, dict[str, str]]]:
	with path.open("r", encoding="utf-8-sig", newline="") as file:
		reader = csv.DictReader(file)
		for row_number, row in enumerate(reader, start=2):
			yield row_number, row


def normalize_captions(value: str) -> str:
	value = value.strip()
	if not value:
		return ""
	try:
		parsed = json.loads(value)
	except json.JSONDecodeError:
		return value
	if isinstance(parsed, list):
		return " ".join(str(item) for item in parsed if item)
	return str(parsed)


def collect_hashes_needing_metadata(inputs: Iterable[Path], limit: int) -> set[str]:
	hashes: set[str] = set()
	for path in inputs:
		for index, (_, row) in enumerate(csv_rows(path), start=1):
			if limit and index > limit:
				break
			if row.get("captions"):
				continue
			sha256 = row.get("sha256", "").strip()
			if sha256:
				hashes.add(sha256)
	return hashes


def load_metadata(metadata_inputs: Iterable[Path], wanted_hashes: set[str]) -> dict[str, Metadata]:
	metadata: dict[str, Metadata] = {}
	if not wanted_hashes:
		return metadata
	for path in metadata_inputs:
		if not path.exists():
			continue
		for _, row in csv_rows(path):
			sha256 = row.get("sha256", "").strip()
			if not sha256 or sha256 not in wanted_hashes or sha256 in metadata:
				continue
			metadata[sha256] = Metadata(
				source=path.name,
				file_identifier=row.get("file_identifier", ""),
				captions=row.get("captions", ""),
				aesthetic_score=row.get("aesthetic_score", ""),
			)
	return metadata


def build_text(row: dict[str, str], metadata: Metadata | None) -> str:
	parts = [normalize_captions(row.get("captions", "")), row.get("file_identifier", ""), row.get("local_path", "")]
	if metadata:
		parts.extend((normalize_captions(metadata.captions), metadata.file_identifier))
	return " ".join(part for part in parts if part)


def classify(text: str) -> tuple[bool, list[str], list[str]]:
	matched_groups: list[str] = []
	matched_terms: list[str] = []
	for group, patterns in FURNITURE_PATTERNS.items():
		group_terms: list[str] = []
		for pattern in patterns:
			for match in re.finditer(pattern, text, re.IGNORECASE):
				group_terms.append(match.group(0))
		if group_terms:
			matched_groups.append(group)
			matched_terms.extend(group_terms)

	unique_terms = sorted(set(term.lower() for term in matched_terms))
	if not matched_groups:
		return False, [], []
	if matched_groups == ["furniture"] and unique_terms == ["table"]:
		if any(pattern.search(text) for pattern in EXCLUDE_IF_ONLY_PATTERNS):
			return False, [], []
	if matched_groups == ["furniture"] and unique_terms == ["bed"] and VEHICLE_BED_PATTERN.search(text):
		return False, [], []
	return True, matched_groups, unique_terms


def compact_evidence(text: str, terms: list[str], width: int = 260) -> str:
	lowered = text.lower()
	positions = [lowered.find(term.lower()) for term in terms if lowered.find(term.lower()) >= 0]
	if not positions:
		return text[:width]
	start = max(0, min(positions) - 80)
	return text[start : start + width].replace("\n", " ")


def analyze_input(path: Path, metadata_by_sha: dict[str, Metadata], out_dir: Path, limit: int) -> dict[str, int | Counter[str]]:
	output_path = out_dir / f"{path.stem}_furniture_candidates.csv"
	stats: dict[str, int | Counter[str]] = {
		"rows": 0,
		"candidates": 0,
		"metadata_matched": 0,
		"missing_text": 0,
		"groups": Counter(),
	}
	with output_path.open("w", encoding="utf-8", newline="") as file:
		writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
		writer.writeheader()
		for index, (row_number, row) in enumerate(csv_rows(path), start=1):
			if limit and index > limit:
				break
			stats["rows"] += 1
			sha256 = row.get("sha256", "").strip()
			metadata = metadata_by_sha.get(sha256)
			if metadata:
				stats["metadata_matched"] += 1
			text = build_text(row, metadata)
			if not text.strip():
				stats["missing_text"] += 1
				continue
			is_furniture, groups, terms = classify(text)
			if not is_furniture:
				continue
			stats["candidates"] += 1
			stats_groups = stats["groups"]
			assert isinstance(stats_groups, Counter)
			stats_groups.update(groups)
			writer.writerow(
				{
					"source_file": path.name,
					"source_row": row_number,
					"sha256": sha256,
					"decision": "furniture_home",
					"matched_groups": ";".join(groups),
					"matched_terms": ";".join(terms),
					"metadata_source": metadata.source if metadata else path.name,
					"aesthetic_score": row.get("aesthetic_score") or (metadata.aesthetic_score if metadata else ""),
					"file_identifier": row.get("file_identifier") or (metadata.file_identifier if metadata else ""),
					"local_path": row.get("local_path", ""),
					"evidence": compact_evidence(text, terms),
				}
			)
	return stats


def write_summary(out_dir: Path, stats_by_file: dict[str, dict[str, int | Counter[str]]], metadata_needed: int, metadata_loaded: int) -> None:
	lines = [
		"# Furniture/Home Data Analysis",
		"",
		"Rule: mark rows as furniture/home when captions, file identifiers, or local paths contain furniture, lighting, home appliance/fixture, or soft-furnishing terms.",
		"",
		f"Metadata hashes needing lookup: {metadata_needed}",
		f"Metadata hashes loaded: {metadata_loaded}",
		"",
		"| input | rows | furniture_home candidates | metadata matched | missing text | top matched groups |",
		"|---|---:|---:|---:|---:|---|",
	]
	totals = defaultdict(int)
	total_groups: Counter[str] = Counter()
	for name, stats in stats_by_file.items():
		groups = stats["groups"]
		assert isinstance(groups, Counter)
		group_text = ", ".join(f"{group}:{count}" for group, count in groups.most_common())
		lines.append(
			f"| {name} | {stats['rows']} | {stats['candidates']} | {stats['metadata_matched']} | {stats['missing_text']} | {group_text} |"
		)
		for key in ("rows", "candidates", "metadata_matched", "missing_text"):
			value = stats[key]
			assert isinstance(value, int)
			totals[key] += value
		total_groups.update(groups)
	lines.append(
		f"| TOTAL | {totals['rows']} | {totals['candidates']} | {totals['metadata_matched']} | {totals['missing_text']} | "
		+ ", ".join(f"{group}:{count}" for group, count in total_groups.most_common())
		+ " |"
	)
	lines.extend(
		[
			"",
			"Candidate CSV files are written next to this summary, one per input file.",
		]
	)
	(out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
	args = parse_args()
	inputs = tuple(args.inputs or DEFAULT_INPUTS)
	metadata_inputs = tuple(args.metadata_inputs or DEFAULT_METADATA_INPUTS)
	args.out_dir.mkdir(parents=True, exist_ok=True)

	metadata_needed = collect_hashes_needing_metadata(inputs, args.limit)
	metadata_by_sha = load_metadata(metadata_inputs, metadata_needed)
	stats_by_file = {
		path.name: analyze_input(path, metadata_by_sha, args.out_dir, args.limit)
		for path in inputs
	}
	write_summary(args.out_dir, stats_by_file, len(metadata_needed), len(metadata_by_sha))
	print(f"Wrote report to {args.out_dir}")


if __name__ == "__main__":
	main()
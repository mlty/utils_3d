#!/usr/bin/env python3
"""Analyze ObjaverseXL captions, quality risks, categories, and numeric metadata."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_filter_llm_api  # noqa: E402


DEFAULT_INPUTS = (
	Path("/Users/mlty/Downloads/ObjaverseXL_github.csv"),
	Path("/Users/mlty/Downloads/ObjaverseXL_sketchfab.csv"),
)
DEFAULT_METADATA_INPUTS = (
	Path("/Users/mlty/Downloads/metadata.csv"),
	Path("/Users/mlty/Downloads/metadata_github.csv"),
)
OUTPUT_FIELDS = (
	"source", "source_row", "sha256", "file_identifier", "aesthetic_score",
	"face_count", "caption_status", "category", "quality_decision",
	"quality_reasons", "caption",
)
FACE_COUNT_FIELDS = (
	"face_count", "faces", "num_faces", "face_num", "polygon_count",
	"poly_count", "triangle_count", "triangles", "num_triangles",
)

CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
	(category, re.compile(pattern, re.IGNORECASE))
	for category, pattern in {
		"human_character": r"\b(character|human|person|man|woman|boy|girl|warrior|soldier|humanoid|knight|zombie)\b",
		"animal_creature": r"\b(animal|creature|monster|dragon|dog|cat|bird|fish|horse|mammal|insect|dinosaur)\b",
		"vehicle": r"\b(car|truck|vehicle|tank|ship|boat|aircraft|airplane|helicopter|motorcycle|bicycle|train|spaceship)\b",
		"furniture_home": r"\b(chair|table|sofa|couch|bed|cabinet|desk|shelf|lamp|furniture|appliance)\b",
		"architecture": r"\b(building|house|tower|bridge|temple|castle|room|wall|door|window|stairs|roof|architecture)\b",
		"weapon": r"\b(sword|gun|rifle|pistol|weapon|axe|bow|shield|cannon|missile|knife|dagger)\b",
		"industrial_tool": r"\b(tool|machine|equipment|engine|robot|mech|drill|hammer|factory|industrial)\b",
		"electronics": r"\b(computer|phone|camera|television|monitor|electronic|console|speaker|keyboard)\b",
		"food_tableware": r"\b(food|fruit|vegetable|cake|bread|bottle|cup|plate|bowl|glass|tableware)\b",
		"clothing_accessory": r"\b(clothing|shirt|dress|coat|shoe|boot|hat|helmet|armor|bag|watch|jewelry)\b",
		"decoration_sculpture": r"\b(statue|sculpture|figurine|decoration|ornament|vase|artwork|monument)\b",
		"nature_environment": r"\b(tree|plant|flower|forest|rock|stone|terrain|mountain|cliff|cave|landscape|environment)\b",
		"toy_game": r"\b(toy|game|dice|chess|puzzle|doll|playground)\b",
		"container_packaging": r"\b(container|box|crate|barrel|package|packaging|can|jar|basket)\b",
	}.items()
)

HARD_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
	(reason, re.compile(pattern, re.IGNORECASE))
	for reason, pattern in {
		"rock_stone_terrain": r"\b(rock|rocks|stone|stones|boulder|cliff|cave|terrain|rubble|gravel|ore|asteroid|lava)\b",
		"broken_damaged_ruin": r"\b(broken|damaged|destroyed|ruined|ruins|wrecked|collapsed|dilapidated|battle[- ]damaged)\b",
		"fragment_debris": r"\b(debris|fragment|fragments|shard|scrap|rubble|partial asset|body part|single tooth)\b",
		"flat_surface": r"\b(flat plane|floor plane|ground plane|background plane|road surface|pavement|sidewalk|terrain tile)\b",
		"scan_photogrammetry": r"\b(3d scan|3d scanned|scanned asset|photogrammetry|reality capture|laser scan)\b",
		"ai_generated": r"\b(ai[- ]generated|ai[- ]created|generated (?:by|with) ai|generative ai|text[- ]to[- ]3d|ai asset)\b",
		"severe_geometry_quality": r"\b(mesh corruption|corrupted mesh|missing parts?|floating geometry|intersecting geometry|severe artifacts?|unrecognizable|rough sculpture)\b",
	}.items()
)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--metadata-input", action="append", type=Path, dest="metadata_inputs")
	parser.add_argument("--objaverse-input", action="append", type=Path, dest="objaverse_inputs")
	parser.add_argument("--status-field", default="64_15_occ4_block_status")
	parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("glb_filter_success_report"))
	parser.add_argument("--workers", type=int, default=100)
	parser.add_argument("--batch-size", type=int, default=30)
	parser.add_argument("--model", default="gpt-5.5")
	parser.add_argument("--ghc-api-url", default="http://localhost:8313")
	parser.add_argument("--timeout-sec", type=int, default=180)
	parser.add_argument("--resume", action="store_true")
	parser.add_argument("--rules-only", action="store_true")
	parser.add_argument("--prepare-only", action="store_true", help="Build the joined success/caption CSV without API calls")
	parser.add_argument("--limit", type=int, default=0, help="Debug limit passed to the filter; 0 processes all eligible rows")
	return parser.parse_args()


def parse_caption(raw_value: str) -> tuple[str, str]:
	value = (raw_value or "").strip()
	if not value:
		return "", "missing"
	try:
		parsed = json.loads(value)
	except json.JSONDecodeError:
		return value, "raw_text"
	if isinstance(parsed, list):
		text = " ".join(str(item).strip() for item in parsed if str(item).strip())
		return text, "parsed" if text else "missing"
	if isinstance(parsed, str):
		return parsed.strip(), "parsed" if parsed.strip() else "missing"
	return json.dumps(parsed, ensure_ascii=False), "parsed"


def parse_number(value: Any) -> float | None:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if math.isfinite(number) else None


def parse_face_count(row: dict[str, str]) -> int | None:
	for field in FACE_COUNT_FIELDS:
		number = parse_number(row.get(field))
		if number is not None and number >= 0:
			return int(number)
	return None


def reservoir_sample(path: Path, sample_size: int, seed: int) -> tuple[list[tuple[int, dict[str, str]]], list[str], int]:
	sample: list[tuple[int, dict[str, str]]] = []
	randomizer = random.Random(seed)
	with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
		reader = csv.DictReader(handle)
		fields = list(reader.fieldnames or [])
		required = {"sha256", "file_identifier", "aesthetic_score", "captions"}
		missing = sorted(required.difference(fields))
		if missing:
			raise ValueError(f"{path}: missing required columns: {', '.join(missing)}")
		row_count = 0
		for row_count, row in enumerate(reader, start=1):
			if len(sample) < sample_size:
				sample.append((row_count, row))
				continue
			replacement = randomizer.randrange(row_count)
			if replacement < sample_size:
				sample[replacement] = (row_count, row)
	sample.sort(key=lambda item: item[0])
	return sample, fields, row_count


def allocate_quotas(total: int, input_count: int) -> list[int]:
	if total < 0:
		raise ValueError("sample size must be non-negative")
	base, remainder = divmod(total, input_count)
	return [base + (index < remainder) for index in range(input_count)]


def classify_category(text: str) -> str:
	matches = [category for category, pattern in CATEGORY_PATTERNS if pattern.search(text)]
	return matches[0] if matches else "other_unknown"


def analyze_row(source: Path, row_index: int, row: dict[str, str], low_aesthetic_threshold: float) -> dict[str, Any]:
	caption, caption_status = parse_caption(row.get("captions", ""))
	searchable = f"{caption} {row.get('file_identifier', '')}"
	reasons = [reason for reason, pattern in HARD_RISK_PATTERNS if pattern.search(searchable)]
	aesthetic_score = parse_number(row.get("aesthetic_score"))
	if aesthetic_score is not None and aesthetic_score < low_aesthetic_threshold:
		reasons.append("low_aesthetic_score")

	if reasons:
		quality_decision = "reject"
	elif caption_status == "missing" or aesthetic_score is None:
		quality_decision = "review"
		reasons.append("missing_caption" if caption_status == "missing" else "missing_aesthetic_score")
	else:
		quality_decision = "keep"

	face_count = parse_face_count(row)
	return {
		"source": source.stem.removeprefix("ObjaverseXL_"),
		"source_row": row_index,
		"sha256": row.get("sha256", ""),
		"file_identifier": row.get("file_identifier", ""),
		"aesthetic_score": "" if aesthetic_score is None else aesthetic_score,
		"face_count": "" if face_count is None else face_count,
		"caption_status": caption_status,
		"category": classify_category(searchable) if caption else "unknown",
		"quality_decision": quality_decision,
		"quality_reasons": ";".join(reasons),
		"caption": caption,
	}


def percentage(count: int, total: int) -> float:
	return round(100.0 * count / total, 2) if total else 0.0


def numeric_distribution(values: Sequence[float], bins: Sequence[tuple[float, float, str]]) -> list[dict[str, Any]]:
	result = []
	for lower, upper, label in bins:
		count = sum(lower <= value < upper for value in values)
		result.append({"bin": label, "count": count, "percentage": percentage(count, len(values))})
	return result


def counter_distribution(counter: Counter[str], total: int, key_name: str) -> list[dict[str, Any]]:
	return [
		{key_name: key, "count": count, "percentage": percentage(count, total)}
		for key, count in counter.most_common()
	]


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
	with path.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=fields)
		writer.writeheader()
		writer.writerows(rows)


def format_distribution(title: str, rows: Sequence[dict[str, Any]], label_key: str) -> list[str]:
	lines = [f"## {title}", "", "| 项目 | 数量 | 占比 |", "|---|---:|---:|"]
	lines.extend(f"| {row[label_key]} | {row['count']} | {row['percentage']:.2f}% |" for row in rows)
	lines.append("")
	return lines


def write_summary(path: Path, summary: dict[str, Any]) -> None:
	lines = [
		f"# ObjaverseXL {summary['sample_size']} 条 Caption 严格筛选分析",
		"",
		f"- 样本数：{summary['sample_size']}",
		f"- 随机种子：{summary['seed']}",
		f"- 低美学分阈值：{summary['low_aesthetic_threshold']}",
		"- 结论口径：caption 硬风险或美学分低于阈值为 reject；缺 caption/分数为 review。",
		"- 限制：caption 规则只能识别文本明确描述的问题，不能替代模型渲染或几何检查。",
		"",
	]
	lines.extend(format_distribution("来源分布", summary["source_distribution"], "source"))
	lines.extend(format_distribution("种类分布", summary["category_distribution"], "category"))
	lines.extend(format_distribution("低质量占比", summary["quality_distribution"], "quality_decision"))
	lines.extend(format_distribution("低质量原因分布", summary["quality_reason_distribution"], "quality_reason"))
	lines.extend(format_distribution("美学评分分布", summary["aesthetic_distribution"], "bin"))
	lines.extend(["## 面数分布", ""])
	if summary["face_count_available"]:
		lines.extend(["| 区间 | 数量 | 占比 |", "|---|---:|---:|"])
		lines.extend(
			f"| {row['bin']} | {row['count']} | {row['percentage']:.2f}% |"
			for row in summary["face_count_distribution"]
		)
	else:
		lines.append("输入 CSV 不包含面数/三角面数字段，因此无法从现有元数据计算面数分布。")
		lines.append("脚本已支持常见 face/polygon/triangle count 字段；补充几何统计列后可直接重跑。")
	lines.append("")
	path.write_text("\n".join(lines), encoding="utf-8")


def prepare_success_caption_csv(
	metadata_inputs: Sequence[Path],
	objaverse_inputs: Sequence[Path],
	status_field: str,
	output_path: Path,
) -> dict[str, Any]:
	metadata_by_sha: dict[str, dict[str, str]] = {}
	metadata_stats: dict[str, dict[str, int]] = {}
	for metadata_path in metadata_inputs:
		counts = Counter()
		with metadata_path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
			reader = csv.DictReader(handle)
			fields = set(reader.fieldnames or [])
			missing = {"sha256", status_field}.difference(fields)
			if missing:
				raise ValueError(f"{metadata_path}: missing columns: {', '.join(sorted(missing))}")
			for row in reader:
				counts["rows"] += 1
				if not (row.get(status_field) or "").strip() == "success":
					continue
				counts["success_rows"] += 1
				sha256 = (row.get("sha256") or "").strip().lower()
				if not sha256:
					counts["success_missing_sha256"] += 1
					continue
				if sha256 in metadata_by_sha:
					counts["success_duplicate_sha256"] += 1
					continue
				metadata_by_sha[sha256] = {
					"metadata_source": metadata_path.name,
					"local_path": row.get("local_path", ""),
					"block_status": row.get(status_field, ""),
					"num_blocks": row.get(status_field.replace("status", "num_blocks"), ""),
				}
		metadata_stats[metadata_path.name] = dict(counts)

	output_path.parent.mkdir(parents=True, exist_ok=True)
	fields = [
		"sha256", "file_identifier", "aesthetic_score", "captions", "metadata_source",
		"local_path", "block_status", "num_blocks", "objaverse_source", "objaverse_row",
	]
	matched_sha256: set[str] = set()
	caption_sha256: set[str] = set()
	source_stats: dict[str, dict[str, int]] = {}
	with output_path.open("w", encoding="utf-8", newline="") as output_handle:
		writer = csv.DictWriter(output_handle, fieldnames=fields)
		writer.writeheader()
		for objaverse_path in objaverse_inputs:
			counts = Counter()
			with objaverse_path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
				reader = csv.DictReader(handle)
				for row_index, row in enumerate(reader, start=1):
					counts["rows"] += 1
					sha256 = (row.get("sha256") or "").strip().lower()
					metadata = metadata_by_sha.get(sha256)
					if metadata is None:
						continue
					counts["matched_success"] += 1
					matched_sha256.add(sha256)
					captions = (row.get("captions") or "").strip()
					if not captions:
						counts["empty_caption"] += 1
						continue
					if sha256 in caption_sha256:
						counts["duplicate_across_sources"] += 1
						continue
					caption_sha256.add(sha256)
					counts["eligible"] += 1
					writer.writerow({
						"sha256": sha256,
						"file_identifier": row.get("file_identifier", ""),
						"aesthetic_score": row.get("aesthetic_score", ""),
						"captions": captions,
						**metadata,
						"objaverse_source": objaverse_path.stem.removeprefix("ObjaverseXL_"),
						"objaverse_row": row_index,
					})
			source_stats[objaverse_path.name] = dict(counts)

	eligible_by_metadata = Counter(metadata_by_sha[sha256]["metadata_source"] for sha256 in caption_sha256)
	return {
		"status_field": status_field,
		"metadata": metadata_stats,
		"objaverse": source_stats,
		"success_unique_sha256": len(metadata_by_sha),
		"matched_success_unique_sha256": len(matched_sha256),
		"eligible_nonempty_caption": len(caption_sha256),
		"eligible_by_metadata": dict(eligible_by_metadata),
		"success_not_found": len(set(metadata_by_sha).difference(matched_sha256)),
		"matched_but_empty_caption": len(matched_sha256.difference(caption_sha256)),
		"eligible_csv": str(output_path),
	}


def configure_strict_filter() -> None:
	extra_risks = {
		"scanned_photogrammetry": r"\b(3d scan|3d scanned|scanned asset|photogrammetry|reality capture|laser scan)\b",
		"ai_generated": r"\b(ai[- ]generated|ai[- ]created|generated (?:by|with) ai|generative ai|text[- ]to[- ]3d|ai asset)\b",
		"unrecognizable_abnormal": r"\b(unrecognizable|unidentifiable|deformed|distorted|stretched|flattened|malformed|abnormal proportions)\b",
		"rough_sculpture_geometry": r"\b(rough sculpture|mesh corruption|corrupted mesh|floating geometry|missing parts?|severe artifacts?)\b",
		"low_value_primitive": r"\b(test mesh|placeholder|primitive (?:cube|sphere|cylinder|torus)|basic geometric shape)\b",
	}
	for tag, pattern in extra_risks.items():
		data_filter_llm_api.RISK_PATTERNS[tag] = re.compile(pattern, re.IGNORECASE)
	data_filter_llm_api.build_llm_prompt = build_strict_llm_prompt
	original_call = data_filter_llm_api.call_ghc_api

	def call_with_backoff(batch: Sequence[Any], args: argparse.Namespace) -> dict[str, Any]:
		response: dict[str, Any] = {}
		for attempt in range(9):
			response = original_call(batch, args)
			error = str(response.get("error", "")).lower()
			if response.get("status") == "ok" or not ("429" in error or "http 5" in error):
				return response
			if attempt < 8:
				delay = min(2**attempt, 30) + random.random() * 3
				time.sleep(delay)
		return response

	data_filter_llm_api.call_ghc_api = call_with_backoff


def build_strict_llm_prompt(batch: Sequence[Any]) -> str:
	items = [{
		"id": result.asset_id,
		"sha256": result.sha256,
		"file_identifier": result.file_identifier,
		"aesthetic_score": result.aesthetic_score,
		"rule_decision": result.rule_decision,
		"rule_risk_tags": result.risk_tags,
		"rule_positive_tags": result.positive_tags,
		"caption": result.caption_text,
	} for result in batch]
	return (
		"你是3D生成训练资产质检专家。只根据caption和URL路径进行严格筛选，判断是否适合高质量、可复用mesh训练。\n"
		"任意一项成立必须reject：主体是岩石、石块、地形、洞穴、悬崖或无独立语义碎块；资产破损、战损、废墟、残缺、断裂；"
		"主体是碎片、局部、残骸；独立物体携带异常大的地板、背景平面；主体不可识别、语义不明确、比例严重异常或畸形；"
		"明确是3D扫描、摄影测量、AI生成或text-to-3D；粗糙雕塑或明确存在严重几何缺陷、缺件、悬浮、穿插、爆面。\n"
		"纯环境场景、道路、地板、墙面、地形块和训练价值极低的测试基础体通常reject；证据不足时review。"
		"低模本身不等于低质量；正常做旧、锈蚀、树皮、毛发和风格化纹理不能单独触发reject。"
		"主体明确完整、语义清晰、无硬风险且可复用时keep。不要因caption含stone/flat等材质或形容词就误判，必须判断主体语义。\n"
		"只返回JSON，不要Markdown。每个输入必须恰好返回一项，id必须原样复制。格式：\n"
		'{"items":[{"id":"...","decision":"keep|review|reject","asset_category":"简短类别",'
		'"bad_for_3d_training":"yes|no|uncertain","rock_stone_irregular_surface":"yes|no|uncertain",'
		'"broken_or_damaged":"yes|no|uncertain","flat_floor_wall_plane":"yes|no|uncertain",'
		'"scene_or_environment":"yes|no|uncertain","clean_object_candidate":"yes|no|uncertain",'
		'"training_value_score":0,"confidence":0.0,"reasons":["简短中文证据"]}]}\n'
		"training_value_score为0到100，reject通常低于40，keep通常高于60。待判断资产：\n"
		+ json.dumps(items, ensure_ascii=False)
	)


def main() -> int:
	args = parse_args()
	metadata_inputs = tuple(args.metadata_inputs or DEFAULT_METADATA_INPUTS)
	objaverse_inputs = tuple(args.objaverse_inputs or DEFAULT_INPUTS)
	all_inputs = (*metadata_inputs, *objaverse_inputs)
	missing_inputs = [str(path) for path in all_inputs if not path.is_file()]
	if missing_inputs:
		raise FileNotFoundError("missing input CSVs: " + ", ".join(missing_inputs))

	args.out_dir.mkdir(parents=True, exist_ok=True)
	eligible_csv = args.out_dir / "success_with_caption.csv"
	input_summary = prepare_success_caption_csv(
		metadata_inputs, objaverse_inputs, args.status_field, eligible_csv,
	)
	(input_summary_path := args.out_dir / "input_summary.json").write_text(
		json.dumps(input_summary, ensure_ascii=False, indent=2), encoding="utf-8",
	)
	print(json.dumps(input_summary, ensure_ascii=False, indent=2), flush=True)
	if args.prepare_only:
		print(f"Prepared eligible input: {eligible_csv}", flush=True)
		return 0

	configure_strict_filter()
	filter_args = [
		str(eligible_csv),
		"--out-dir", str(args.out_dir / "filter"),
		"--workers", str(args.workers),
		"--batch-size", str(args.batch_size),
		"--model", args.model,
		"--ghc-api-url", args.ghc_api_url,
		"--timeout-sec", str(args.timeout_sec),
		"--llm-scope", "candidates",
	]
	if args.resume:
		filter_args.append("--resume")
	if args.rules_only:
		filter_args.append("--rules-only")
	if args.limit:
		filter_args.extend(("--limit", str(args.limit)))
	return data_filter_llm_api.main(filter_args)


if __name__ == "__main__":
	raise SystemExit(main())

#!/usr/bin/env python3
"""Audit CSV-scoped TexVerse assets with GPT-5.5 caption and image review."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ASSET_ID_PATTERN = re.compile(r"([0-9a-f]{32})(?:_\d+)?\.glb$", re.IGNORECASE)
AI_GENERATED_PATTERN = re.compile(
	r"\b(?:ai[- ]generated|ai[- ]created|generated (?:by|with) ai|generative ai|"
	r"text[- ]to[- ]3d|ai asset)\b|AI生成|人工智能生成|AI资产",
	re.IGNORECASE,
)
RESULT_SCHEMA_VERSION = 7
RESULT_FIELDS = [
	"asset_id", "status", "filter_decision", "asset_category", "asset_subcategory",
	"is_rock_or_stone", "rough_irregular_surface", "is_scanned_asset", "is_ai_generated_asset", "low_quality",
	"broken_or_damaged", "battle_damaged", "debris_or_fragment", "large_floor_plane",
	"unrecognizable_object", "abnormal_proportions", "rough_sculpture",
	"geometry_integrity", "scan_artifacts", "background_residue",
	"texture_quality", "material_quality", "completeness", "object_separability",
	"semantic_clarity", "training_reusability", "image_assessability",
	"caption_image_consistency", "reject_severity", "confidence", "quality_issues",
	"reason", "name", "caption", "thumbnail_url", "error",
]
ENUM_FIELDS = {
	"filter_decision": {"keep", "reject", "review"},
	"is_rock_or_stone": {"yes", "no", "uncertain"},
	"rough_irregular_surface": {"yes", "no", "uncertain"},
	"is_scanned_asset": {"yes", "no", "uncertain"},
	"is_ai_generated_asset": {"yes", "no", "uncertain"},
	"low_quality": {"yes", "no", "uncertain"},
	"broken_or_damaged": {"yes", "no", "uncertain"},
	"battle_damaged": {"yes", "no", "uncertain"},
	"debris_or_fragment": {"yes", "no", "uncertain"},
	"large_floor_plane": {"yes", "no", "uncertain"},
	"unrecognizable_object": {"yes", "no", "uncertain"},
	"abnormal_proportions": {"yes", "no", "uncertain"},
	"rough_sculpture": {"yes", "no", "uncertain"},
	"geometry_integrity": {"good", "minor_issue", "severe_issue", "uncertain"},
	"scan_artifacts": {"none", "minor", "severe", "uncertain"},
	"background_residue": {"none", "minor", "severe", "uncertain"},
	"texture_quality": {"good", "acceptable", "poor", "uncertain"},
	"material_quality": {"good", "acceptable", "poor", "uncertain"},
	"completeness": {"complete", "partial", "broken", "uncertain"},
	"object_separability": {"clean", "mixed", "fused", "uncertain"},
	"semantic_clarity": {"clear", "ambiguous", "invalid", "uncertain"},
	"training_reusability": {"high", "medium", "low", "uncertain"},
	"image_assessability": {"good", "limited", "unusable", "uncertain"},
	"caption_image_consistency": {"consistent", "conflict", "uncertain"},
	"reject_severity": {"none", "soft", "hard"},
}
QUALITY_ISSUES = {
	"rock_stone", "rough_surface", "scan_noise", "hole", "fragmented", "floating",
	"missing_part", "mesh_corruption", "background_residue", "unrelated_objects",
	"poor_geometry", "texture_missing", "texture_blurry", "texture_stretched",
	"texture_artifact", "material_error", "partial_asset", "fused_objects",
	"semantic_mismatch", "battle_damage", "debris", "large_floor_plane",
	"unrecognizable", "abnormal_proportions", "rough_sculpture", "ruin",
	"ai_generated", "too_dark", "too_small", "occluded", "other",
}
CATEGORY_VALUES = {
	"natural_environment", "architecture", "furniture_home", "industrial_tool",
	"vehicle", "electronics", "food_tableware", "clothing_accessory", "human_body",
	"animal", "weapon", "decoration_sculpture", "container_packaging", "toy_game",
	"other", "unknown",
}


def normalize_responses_url(raw_url: Optional[str]) -> str:
	url = (raw_url or "http://localhost:8313").rstrip("/")
	if url.endswith("/responses"):
		return url
	if url.endswith("/chat/completions"):
		return url.removesuffix("/chat/completions") + "/responses"
	if url.endswith("/v1"):
		return url + "/responses"
	return url + "/v1/responses"


def extract_response_text(response_json: Dict[str, Any]) -> str:
	if isinstance(response_json.get("output_text"), str):
		return response_json["output_text"]
	parts: List[str] = []
	for item in response_json.get("output", []):
		if not isinstance(item, dict):
			continue
		for part in item.get("content", []):
			if isinstance(part, dict):
				text = part.get("text") or part.get("output_text")
				if isinstance(text, str):
					parts.append(text)
	return "".join(parts)


def extract_json_object(text: str) -> Dict[str, Any]:
	try:
		value = json.loads(text)
	except json.JSONDecodeError:
		match = re.search(r"\{.*\}", text, re.DOTALL)
		if not match:
			raise
		value = json.loads(match.group(0))
	if not isinstance(value, dict):
		raise ValueError("model response is not a JSON object")
	return value


def has_explicit_ai_generation_claim(record: Dict[str, Any]) -> bool:
	text = "\n".join(str(record.get(field, "")) for field in ("name", "metadata_description", "caption"))
	return AI_GENERATED_PATTERN.search(text) is not None


def normalize_result(raw_result: Dict[str, Any]) -> Dict[str, Any]:
	result: Dict[str, Any] = {}
	category = str(raw_result.get("asset_category", "unknown")).strip().lower()
	result["asset_category"] = category if category in CATEGORY_VALUES else "other"
	result["asset_subcategory"] = str(raw_result.get("asset_subcategory", "")).strip()[:100]
	for field, allowed in ENUM_FIELDS.items():
		default = "review" if field == "filter_decision" else "uncertain"
		if field == "reject_severity":
			default = "none"
		value = str(raw_result.get(field, default)).strip().lower()
		result[field] = value if value in allowed else default
	try:
		result["confidence"] = max(0.0, min(1.0, float(raw_result.get("confidence", 0.0))))
	except (TypeError, ValueError):
		result["confidence"] = 0.0
	issues = raw_result.get("quality_issues", [])
	if not isinstance(issues, list):
		issues = []
	result["quality_issues"] = list(dict.fromkeys(
		str(issue).strip().lower() if str(issue).strip().lower() in QUALITY_ISSUES else "other"
		for issue in issues if str(issue).strip()
	))
	result["reason"] = str(raw_result.get("reason", "")).strip()[:500]
	strict_reject_fields = {
		"is_scanned_asset", "is_ai_generated_asset", "broken_or_damaged", "battle_damaged", "debris_or_fragment",
		"large_floor_plane", "unrecognizable_object", "abnormal_proportions",
		"rough_sculpture",
	}
	severe_quality_issue = (
		result["geometry_integrity"] == "severe_issue" or
		result["scan_artifacts"] == "severe" or
		result["background_residue"] == "severe" or
		result["texture_quality"] == "poor" or
		result["material_quality"] == "poor" or
		result["completeness"] == "broken" or
		result["object_separability"] == "fused" or
		result["semantic_clarity"] == "invalid"
	)
	strict_reject = (
		any(result[field] == "yes" for field in strict_reject_fields) or
		result["is_rock_or_stone"] == "yes" or severe_quality_issue
	)
	if strict_reject:
		result["reject_severity"] = "hard"
	elif result["reject_severity"] == "hard":
		result["reject_severity"] = "soft"
	if result["filter_decision"] == "reject" and result["reject_severity"] != "hard":
		result["filter_decision"] = "review"
	if result["reject_severity"] == "hard":
		result["filter_decision"] = "reject"
	return result


def build_prompt(record: Dict[str, Any]) -> str:
	return (
		"你是3D生成训练资产视觉质检专家。结合缩略图、caption和metadata，判断资产是否适合高质量、可复用mesh训练。\n"
		"以下硬拒绝条件相互独立，满足任意一条就必须reject并设置reject_severity=hard，不需要同时满足多条：\n"
		"注意：rough_irregular_surface仅用于记录表面特征，不能单独触发reject。正常树皮、毛发、织物、皮革、"
		"做旧、锈蚀、雕刻、颗粒材质和风格化纹理即使视觉粗糙，只要几何完整可识别，也不能仅凭粗糙拒绝。\n"
		"A. 主体是石头、岩石、碎石、矿石、洞穴、悬崖、土堆、断壁残垣或没有独立语义的小碎块。\n"
		"B. 结构上有大范围破损、战损、残缺、断裂等，包括损坏车辆、损坏房屋、损坏墙面、废墟和断壁残垣。"
		"这是数据要求，不因破损是设计意图而保留。\n"
		"C. 独立物体携带明显大于主体占地的大面积地板、底部平面、扫描平台或背景平面时必须拒绝。"
		"重点识别主体很小、平面向四周延伸很远、平面面积显著大于物体投影面积的情况，并设置 large_floor_plane=yes。"
		"正常房间/完整场景中的合理地面，以及紧贴主体轮廓、面积与主体相近的装饰性小底座，不算异常大平面。\n"
		"D. 主体是单个牙齿、碎片、碎块或不完整局部。\n"
		"E. 无法识别、不合理、语义不明确，或caption/name/description也不能可靠解释主体。\n"
		"F. 明显过长、过扁、比例失真、拉伸、压扁、畸形或其他异常物体，且不是可识别物体的正常设计。\n"
		"G. 明确属于3D扫描或摄影测量资产时必须拒绝，即is_scanned_asset=yes单独就足以reject，"
		"无论表面是否干净、是否存在明显扫描噪声。\n"
		"H. caption、name、metadata或图片明确提到或表明是AI生成、AI资产、generative AI、text-to-3D、"
		"AI-generated时必须拒绝，并设置is_ai_generated_asset=yes；只要明确提到即可，不要求同时存在视觉缺陷。\n"
		"I. rough_sculpture=yes，或存在严重几何缺陷、扫描缺陷、背景残留、纹理或材质问题，包括关键部件缺失、"
		"悬浮、错位、穿插、爆面、多个无关对象融合、"
		"极低几何质量或严重纹理/材质错误。\n"
		"keep：主体明确完整、视觉质量合格且可复用，没有硬拒绝问题。\n"
		"review：只有轻微问题；图片过暗/过小/遮挡；caption冲突；扫描或设计意图不确定；证据不足。\n"
		"caption/name/metadata必须用于判断类别、石头、废墟、战损、碎块、扫描件、AI生成资产等语义；图片用于核实外观。"
		"caption明确描述上述禁用内容且图片不冲突时应reject。低模本身不等于低质量，但任何明确破损/战损仍拒绝。\n"
		"asset_category只能是 natural_environment|architecture|furniture_home|industrial_tool|vehicle|electronics|"
		"food_tableware|clothing_accessory|human_body|animal|weapon|decoration_sculpture|container_packaging|toy_game|other|unknown。\n"
		"只返回JSON，不要Markdown，必须包含以下字段：\n"
		"{\"filter_decision\":\"keep|reject|review\",\"asset_category\":\"固定类别\",\"asset_subcategory\":\"简短子类\","
		"\"is_rock_or_stone\":\"yes|no|uncertain\",\"rough_irregular_surface\":\"yes|no|uncertain\","
		"\"is_scanned_asset\":\"yes|no|uncertain\",\"is_ai_generated_asset\":\"yes|no|uncertain\","
		"\"low_quality\":\"yes|no|uncertain\","
		"\"broken_or_damaged\":\"yes|no|uncertain\",\"battle_damaged\":\"yes|no|uncertain\","
		"\"debris_or_fragment\":\"yes|no|uncertain\",\"large_floor_plane\":\"yes|no|uncertain\","
		"\"unrecognizable_object\":\"yes|no|uncertain\",\"abnormal_proportions\":\"yes|no|uncertain\","
		"\"rough_sculpture\":\"yes|no|uncertain\",\"geometry_integrity\":\"good|minor_issue|severe_issue|uncertain\","
		"\"scan_artifacts\":\"none|minor|severe|uncertain\",\"background_residue\":\"none|minor|severe|uncertain\","
		"\"texture_quality\":\"good|acceptable|poor|uncertain\",\"material_quality\":\"good|acceptable|poor|uncertain\","
		"\"completeness\":\"complete|partial|broken|uncertain\",\"object_separability\":\"clean|mixed|fused|uncertain\","
		"\"semantic_clarity\":\"clear|ambiguous|invalid|uncertain\",\"training_reusability\":\"high|medium|low|uncertain\","
		"\"image_assessability\":\"good|limited|unusable|uncertain\","
		"\"caption_image_consistency\":\"consistent|conflict|uncertain\",\"reject_severity\":\"none|soft|hard\","
		"\"confidence\":0.0,\"quality_issues\":[\"标准问题标签\"],\"reason\":\"简短中文图片证据\"}\n"
		"quality_issues可选：rock_stone,rough_surface,scan_noise,hole,fragmented,floating,missing_part,mesh_corruption,"
		"background_residue,unrelated_objects,poor_geometry,texture_missing,texture_blurry,texture_stretched,texture_artifact,"
		"material_error,partial_asset,fused_objects,semantic_mismatch,battle_damage,debris,large_floor_plane,unrecognizable,"
		"abnormal_proportions,rough_sculpture,ruin,ai_generated,too_dark,too_small,occluded,other。\n"
		f"asset_id: {record['asset_id']}\nname: {record['name']}\n"
		f"metadata_description: {record['metadata_description']}\ncaption: {record['caption']}"
	)

def fetch_image_data_url(url: str, timeout_sec: int) -> str:
	request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
	with urllib.request.urlopen(request, timeout=timeout_sec) as response:
		content = response.read()
		mime_type = response.headers.get_content_type() or "image/jpeg"
	return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"


def make_payload(record: Dict[str, Any], model: str, image_data_url: Optional[str]) -> Dict[str, Any]:
	if image_data_url:
		model_input: Any = [{"role": "user", "content": [
			{"type": "input_text", "text": build_prompt(record)},
			{"type": "input_image", "image_url": image_data_url},
		]}]
	else:
		model_input = build_prompt(record) + (
			"\n图片因内容策略无法处理。只能辅助分类；filter_decision必须为review，所有视觉质量字段为uncertain。"
		)
	return {"model": model, "input": model_input}


def request_model(record: Dict[str, Any], args: argparse.Namespace, image_data_url: Optional[str]) -> Dict[str, Any]:
	headers = {"Content-Type": "application/json"}
	api_key = os.environ.get(args.ghc_api_key_env, "")
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"
	request = urllib.request.Request(
		normalize_responses_url(args.ghc_api_url),
		data=json.dumps(make_payload(record, args.model, image_data_url)).encode("utf-8"),
		headers=headers,
		method="POST",
	)
	with urllib.request.urlopen(request, timeout=args.timeout_sec) as response:
		response_json = json.loads(response.read().decode("utf-8"))
	raw_result = extract_json_object(extract_response_text(response_json))
	if has_explicit_ai_generation_claim(record):
		raw_result["is_ai_generated_asset"] = "yes"
		issues = raw_result.get("quality_issues")
		raw_result["quality_issues"] = [*issues, "ai_generated"] if isinstance(issues, list) else ["ai_generated"]
	return normalize_result(raw_result)


def review_record(record: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
	last_error = ""
	for attempt in range(args.retries + 1):
		image_data_url: Optional[str] = None
		try:
			image_data_url = fetch_image_data_url(record["thumbnail_url"], args.timeout_sec)
			result = request_model(record, args, image_data_url)
			return {**record, "schema_version": RESULT_SCHEMA_VERSION, "status": "ok", "result": result, "error": ""}
		except urllib.error.HTTPError as exc:
			detail = exc.read().decode("utf-8", errors="replace")[-1500:]
			last_error = f"HTTP {exc.code}: {detail}"
			image_unavailable = image_data_url is None and exc.code in {403, 404, 410}
			image_blocked = exc.code == 400 and "image processing blocked" in detail.lower()
			if image_unavailable or image_blocked:
				try:
					result = request_model(record, args, None)
					explicit_ai_generated = has_explicit_ai_generation_claim(record)
					result.update({
						"filter_decision": "reject" if explicit_ai_generated else "review",
						"is_rock_or_stone": "uncertain",
						"rough_irregular_surface": "uncertain", "is_scanned_asset": "uncertain",
						"is_ai_generated_asset": "yes" if explicit_ai_generated else "uncertain",
						"low_quality": "uncertain", "broken_or_damaged": "uncertain",
						"battle_damaged": "uncertain", "debris_or_fragment": "uncertain",
						"large_floor_plane": "uncertain", "unrecognizable_object": "uncertain",
						"abnormal_proportions": "uncertain", "rough_sculpture": "uncertain",
						"geometry_integrity": "uncertain", "scan_artifacts": "uncertain",
						"background_residue": "uncertain", "texture_quality": "uncertain",
						"material_quality": "uncertain", "completeness": "uncertain",
						"object_separability": "uncertain", "semantic_clarity": "uncertain",
						"training_reusability": "uncertain", "image_assessability": "unusable",
						"caption_image_consistency": "uncertain",
						"reject_severity": "hard" if explicit_ai_generated else "none",
						"quality_issues": ["ai_generated"] if explicit_ai_generated else [],
						"reason": "文本明确表明是AI生成资产。" if explicit_ai_generated else
							"缩略图不可用，无法进行视觉质量判断。" if image_unavailable else
							"图片被内容策略阻止，无法进行视觉质量判断。",
					})
					result = normalize_result(result)
					status = "image_unavailable_caption_only" if image_unavailable else "image_blocked_caption_only"
					return {**record, "schema_version": RESULT_SCHEMA_VERSION, "status": status, "result": result, "error": last_error}
				except Exception as fallback_exc:
					last_error += f"; fallback failed: {type(fallback_exc).__name__}: {fallback_exc}"
				break
			if exc.code < 500 and exc.code != 429:
				break
		except Exception as exc:
			last_error = f"{type(exc).__name__}: {exc}"
		if attempt < args.retries:
			time.sleep(min(2**attempt, 8))
	return {**record, "schema_version": RESULT_SCHEMA_VERSION, "status": "failed", "result": {}, "error": last_error}


def asset_id_from_path(local_path: str) -> str:
	match = ASSET_ID_PATTERN.search(local_path)
	return match.group(1).lower() if match else ""


def asset_id_from_row(source_row: Dict[str, str]) -> str:
	asset_id = str(source_row.get("asset_id", "")).strip().lower()
	if re.fullmatch(r"[0-9a-f]{32}", asset_id):
		return asset_id
	return asset_id_from_path(source_row.get("local_path", ""))


def load_sample(args: argparse.Namespace) -> tuple[List[Dict[str, Any]], List[str], Dict[str, int]]:
	with Path(args.metadata).open(encoding="utf-8") as handle:
		metadata = json.load(handle)
	with Path(args.captions).open(encoding="utf-8") as handle:
		captions = json.load(handle)
	with Path(args.input_csv).open(encoding="utf-8-sig", newline="") as handle:
		reader = csv.DictReader(handle)
		source_fields = list(reader.fieldnames or [])
		source_rows = list(reader)

	eligible: List[Dict[str, Any]] = []
	missing_caption = 0
	duplicate_assets = 0
	seen_asset_ids = set()
	for source_index, source_row in enumerate(source_rows):
		asset_id = asset_id_from_row(source_row)
		item = metadata.get(asset_id)
		caption = captions.get(asset_id)
		if not asset_id or not isinstance(item, dict) or not item.get("thumbnail_url"):
			continue
		if not isinstance(caption, str) or not caption.strip():
			missing_caption += 1
			continue
		if args.deduplicate_assets and asset_id in seen_asset_ids:
			duplicate_assets += 1
			continue
		seen_asset_ids.add(asset_id)
		eligible.append({
			"asset_id": asset_id, "source_index": source_index, "source_row": source_row,
			"name": str(item.get("name", "")), "metadata_description": str(item.get("description", "")),
			"caption": caption, "thumbnail_url": str(item["thumbnail_url"]),
		})
	sample_size = len(eligible) if args.all else min(max(args.sample_size, 0), len(eligible))
	sample = eligible if args.all else random.Random(args.seed).sample(eligible, sample_size)
	sample.sort(key=lambda record: int(record["source_index"]))
	stats = {
		"source_rows": len(source_rows), "eligible_rows": len(eligible),
		"missing_caption": missing_caption, "duplicate_assets": duplicate_assets,
	}
	return sample, source_fields, stats


def flat_result(record: Dict[str, Any], source_fields: Sequence[str]) -> Dict[str, Any]:
	result = record.get("result") if isinstance(record.get("result"), dict) else {}
	issues = result.get("quality_issues", [])
	row = {field: record.get("source_row", {}).get(field, "") for field in source_fields}
	row.update({
		"asset_id": record.get("asset_id", ""), "status": record.get("status", ""),
		"filter_decision": result.get("filter_decision", ""), "asset_category": result.get("asset_category", ""),
		"asset_subcategory": result.get("asset_subcategory", ""),
		"is_rock_or_stone": result.get("is_rock_or_stone", ""),
		"rough_irregular_surface": result.get("rough_irregular_surface", ""),
		"is_scanned_asset": result.get("is_scanned_asset", ""),
		"is_ai_generated_asset": result.get("is_ai_generated_asset", ""), "low_quality": result.get("low_quality", ""),
		"broken_or_damaged": result.get("broken_or_damaged", ""),
		"battle_damaged": result.get("battle_damaged", ""),
		"debris_or_fragment": result.get("debris_or_fragment", ""),
		"large_floor_plane": result.get("large_floor_plane", ""),
		"unrecognizable_object": result.get("unrecognizable_object", ""),
		"abnormal_proportions": result.get("abnormal_proportions", ""),
		"rough_sculpture": result.get("rough_sculpture", ""),
		"geometry_integrity": result.get("geometry_integrity", ""), "scan_artifacts": result.get("scan_artifacts", ""),
		"background_residue": result.get("background_residue", ""), "texture_quality": result.get("texture_quality", ""),
		"material_quality": result.get("material_quality", ""), "completeness": result.get("completeness", ""),
		"object_separability": result.get("object_separability", ""), "semantic_clarity": result.get("semantic_clarity", ""),
		"training_reusability": result.get("training_reusability", ""),
		"image_assessability": result.get("image_assessability", ""),
		"caption_image_consistency": result.get("caption_image_consistency", ""),
		"reject_severity": result.get("reject_severity", ""), "confidence": result.get("confidence", ""),
		"quality_issues": "; ".join(str(value) for value in issues) if isinstance(issues, list) else str(issues),
		"reason": result.get("reason", ""), "name": record.get("name", ""),
		"caption": record.get("caption", ""), "thumbnail_url": record.get("thumbnail_url", ""),
		"error": record.get("error", ""),
	})
	return row


def read_completed(out_dir: Path) -> Dict[str, Dict[str, Any]]:
	path = out_dir / "results.jsonl"
	if not path.exists():
		return {}
	completed: Dict[str, Dict[str, Any]] = {}
	with path.open(encoding="utf-8") as handle:
		for line in handle:
			try:
				record = json.loads(line)
			except json.JSONDecodeError:
				continue
			if (record.get("asset_id") and record.get("status") != "failed" and
					record.get("schema_version") == RESULT_SCHEMA_VERSION):
				completed[str(record["asset_id"])] = record
	return completed


def append_checkpoint(out_dir: Path, record: Dict[str, Any]) -> None:
	out_dir.mkdir(parents=True, exist_ok=True)
	with (out_dir / "results.jsonl").open("a", encoding="utf-8") as handle:
		handle.write(json.dumps(record, ensure_ascii=False) + "\n")
		handle.flush()


def write_outputs(records: Sequence[Dict[str, Any]], source_fields: Sequence[str], stats: Dict[str, int], args: argparse.Namespace) -> None:
	out_dir = Path(args.out_dir)
	out_dir.mkdir(parents=True, exist_ok=True)
	ordered = sorted(records, key=lambda record: int(record.get("source_index", 0)))
	with (out_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
		for record in ordered:
			handle.write(json.dumps(record, ensure_ascii=False) + "\n")
	output_fields = list(source_fields) + RESULT_FIELDS
	rows = [flat_result(record, source_fields) for record in ordered]
	selections = {
		"results.csv": rows,
		"keep.csv": [row for row in rows if row["filter_decision"] == "keep"],
		"reject.csv": [row for row in rows if row["filter_decision"] == "reject"],
		"review.csv": [row for row in rows if row["filter_decision"] == "review"],
	}
	for filename, selected in selections.items():
		with (out_dir / filename).open("w", encoding="utf-8", newline="") as handle:
			writer = csv.DictWriter(handle, fieldnames=output_fields)
			writer.writeheader()
			writer.writerows(selected)
	decisions = Counter(row["filter_decision"] for row in rows)
	issues = Counter(issue.strip() for row in rows for issue in row["quality_issues"].split(";") if issue.strip())
	dimension_fields = [
		"asset_category", "is_rock_or_stone", "rough_irregular_surface", "is_scanned_asset", "is_ai_generated_asset", "low_quality",
		"broken_or_damaged", "battle_damaged", "debris_or_fragment", "large_floor_plane",
		"unrecognizable_object", "abnormal_proportions", "rough_sculpture",
		"geometry_integrity", "scan_artifacts", "background_residue", "texture_quality",
		"material_quality", "completeness", "object_separability", "semantic_clarity",
		"training_reusability", "image_assessability", "caption_image_consistency", "reject_severity",
	]
	summary = {
		"schema_version": RESULT_SCHEMA_VERSION, "model": args.model, "seed": args.seed,
		"all": args.all, "sample_size": len(rows), **stats,
		"status_counts": dict(Counter(row["status"] for row in rows)),
		"decision_counts": dict(decisions), "quality_issue_counts": dict(issues),
		"dimension_counts": {
			field: dict(Counter(row[field] or "missing" for row in rows)) for field in dimension_fields
		},
	}
	with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
		json.dump(summary, handle, ensure_ascii=False, indent=2)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--input-csv", default="/Users/mlty/Downloads/metadata (1).csv")
	parser.add_argument("--metadata", default="/Users/mlty/Downloads/metadata.json")
	parser.add_argument("--captions", default="/Users/mlty/Downloads/caption.json")
	parser.add_argument("--out-dir", default="data_filter/texverse/filter_mask_report_100")
	parser.add_argument("--sample-size", type=int, default=100)
	parser.add_argument("--all", action="store_true", help="process every eligible CSV row; ignores --sample-size")
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument("--model", default="gpt-5.5")
	parser.add_argument("--ghc-api-url", default=os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL") or "http://localhost:8313")
	parser.add_argument("--ghc-api-key-env", default="GHC_API_KEY")
	parser.add_argument("--workers", type=int, default=4)
	parser.add_argument("--timeout-sec", type=int, default=180)
	parser.add_argument("--retries", type=int, default=2)
	parser.add_argument("--resume", action="store_true")
	parser.add_argument("--deduplicate-assets", action="store_true", help="process each asset_id only once")
	return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
	args = parse_args(argv)
	sample, source_fields, stats = load_sample(args)
	out_dir = Path(args.out_dir)
	completed = read_completed(out_dir) if args.resume else {}
	if not args.resume:
		out_dir.mkdir(parents=True, exist_ok=True)
		(out_dir / "results.jsonl").write_text("", encoding="utf-8")
	results: List[Dict[str, Any]] = [completed[record["asset_id"]] for record in sample if record["asset_id"] in completed]
	pending = [record for record in sample if record["asset_id"] not in completed]
	print(f"source={stats['source_rows']} eligible={stats['eligible_rows']} sample={len(sample)} pending={len(pending)}")
	started = time.time()
	worker_count = max(args.workers, 1)
	completed_count = 0
	with ThreadPoolExecutor(max_workers=worker_count) as executor:
		pending_iter = iter(pending)
		futures = {
			executor.submit(review_record, record, args)
			for record in (next(pending_iter, None) for _ in range(worker_count))
			if record is not None
		}
		while futures:
			done, futures = wait(futures, return_when=FIRST_COMPLETED)
			for future in done:
				record = future.result()
				results.append(record)
				append_checkpoint(out_dir, record)
				completed_count += 1
				print(f"\rcompleted {completed_count}/{len(pending)}", end="", flush=True)
				next_record = next(pending_iter, None)
				if next_record is not None:
					futures.add(executor.submit(review_record, next_record, args))
	print()
	write_outputs(results, source_fields, stats, args)
	successful = {"ok", "image_blocked_caption_only", "image_unavailable_caption_only"}
	failures = sum(record.get("status") not in successful for record in results)
	print(f"finished in {time.time() - started:.1f}s; failures={failures}; output={out_dir}")
	return 1 if failures else 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except KeyboardInterrupt:
		print("interrupted", file=sys.stderr)
		raise SystemExit(130)

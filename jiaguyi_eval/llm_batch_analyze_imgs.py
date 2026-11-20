

#!/usr/bin/env python3
"""Batch classify image-only AI assets with an OpenAI-compatible ghc-api."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DEFAULT_IMAGE_PATHS = [
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶8815/imgs/手办_玩偶8815_image_000_image_0.png",
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶8800/imgs/手办_玩偶8800_image_000_image_0.png",
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶6861/imgs/手办_玩偶6861_image_003_Image_0.png",
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶7795/imgs/手办_玩偶7795_image_004_Image_0.png",
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶8037/imgs/手办_玩偶8037_image_000_image_0.png",
	"/Users/mlty/Data/jiaguyi6/手办_不包含PBR和骨骼_写实风_13435/手办_玩偶/手办_玩偶8354/imgs/手办_玩偶8354_image_000_image_0.png",
]

CSV_FIELDS = [
	"image_path",
	"status",
	"decision",
	"is_ai_asset",
	"confidence",
	"ai_evidence",
	"normal_evidence",
	"reason",
	"error",
]


def normalize_ghc_chat_url(raw_url: Optional[str]) -> str:
	url = (raw_url or "http://localhost:8313").rstrip("/")
	if url.endswith("/chat/completions"):
		return url
	if url.endswith("/v1"):
		return url + "/chat/completions"
	return url + "/v1/chat/completions"


def normalize_model_name(model: str) -> str:
	model_aliases = {
		"opus-4.8": "claude-opus-4.8",
	}
	return model_aliases.get(model, model)


def image_to_data_url(path: str) -> str:
	mime_type = mimetypes.guess_type(path)[0] or "image/png"
	with open(path, "rb") as handle:
		encoded = base64.b64encode(handle.read()).decode("ascii")
	return f"data:{mime_type};base64,{encoded}"


def extract_json_object(text: str) -> Dict[str, Any]:
	try:
		parsed = json.loads(text)
		return parsed if isinstance(parsed, dict) else {"raw": parsed}
	except json.JSONDecodeError:
		match = re.search(r"\{.*\}", text, re.DOTALL)
		if not match:
			raise
		parsed = json.loads(match.group(0))
		return parsed if isinstance(parsed, dict) else {"raw": parsed}


def read_image_paths(args: argparse.Namespace) -> List[str]:
	paths: List[str] = []
	if args.paths_file:
		with open(args.paths_file, "r", encoding="utf-8") as handle:
			paths.extend(line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#"))
	paths.extend(args.image_paths)
	if not paths:
		paths.extend(DEFAULT_IMAGE_PATHS)
	return sorted(dict.fromkeys(paths))


def build_prompt(image_path: str) -> str:
	return (
		"你是3D资产贴图/图片质检专家。请只根据这张图片判断它是否是AI资产。\n"
		"AI资产判定标准：\n"
		"1）画面由碎片填满；\n"
		"2）无法识别分割的部件，如眼睛、手、身体、可复用部件等；\n"
		"3）没有规整分割区域，比如矩形、圆形、三角形等。\n"
		"正常资产判定标准：\n"
		"1）有可拆分的部件，如眼睛、手、身体、可复用部件等；\n"
		"2）有明显区域，比如矩形、圆形、三角形等；\n"
		"3）有可识别实体或部件；\n"
		"4）画面有实际意义，可识别。\n"
		"只返回JSON，不要返回Markdown。字段必须包含：\n"
		"{\n"
		"  \"decision\": \"ai_asset|normal_asset|review\",\n"
		"  \"is_ai_asset\": \"yes|no|uncertain\",\n"
		"  \"confidence\": 0.0,\n"
		"  \"signals\": {\n"
		"    \"fragment_filled\": \"yes|no|uncertain\",\n"
		"    \"unrecognizable_parts\": \"yes|no|uncertain\",\n"
		"    \"no_regular_regions\": \"yes|no|uncertain\",\n"
		"    \"detachable_parts\": \"yes|no|uncertain\",\n"
		"    \"obvious_regular_regions\": \"yes|no|uncertain\",\n"
		"    \"recognizable_entity_or_parts\": \"yes|no|uncertain\",\n"
		"    \"meaningful_image\": \"yes|no|uncertain\"\n"
		"  },\n"
		"  \"ai_evidence\": [\"...\"],\n"
		"  \"normal_evidence\": [\"...\"],\n"
		"  \"reason\": \"...\"\n"
		"}\n"
		f"图片路径：{image_path}"
	)


def call_ghc_api(image_path: str, args: argparse.Namespace) -> Dict[str, Any]:
	if not os.path.exists(image_path):
		return {"image_path": image_path, "status": "missing_image", "error": "image does not exist"}

	api_url = normalize_ghc_chat_url(args.ghc_api_url)
	content = [
		{"type": "text", "text": build_prompt(image_path)},
		{"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
	]
	payload = {
		"model": normalize_model_name(args.model),
		"messages": [{"role": "user", "content": content}],
		"temperature": args.temperature,
		"response_format": {"type": "json_object"},
	}
	headers = {"Content-Type": "application/json"}
	api_key = os.environ.get(args.ghc_api_key_env, "")
	if api_key:
		headers["Authorization"] = f"Bearer {api_key}"
	request = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

	try:
		with urllib.request.urlopen(request, timeout=args.timeout_sec) as response:
			response_json = json.loads(response.read().decode("utf-8"))
		content_text = response_json["choices"][0]["message"].get("content", "")
		parsed = extract_json_object(content_text)
		return {"image_path": image_path, "status": "ok", "response": parsed, "raw_response": response_json}
	except urllib.error.HTTPError as exc:
		error_text = exc.read().decode("utf-8", errors="replace")[-2000:]
		return {"image_path": image_path, "status": "failed", "error": f"HTTP {exc.code}: {error_text}"}
	except Exception as exc:
		return {"image_path": image_path, "status": "failed", "error": str(exc)}


def compact_list(value: Any) -> str:
	if isinstance(value, list):
		return "; ".join(str(item) for item in value)
	if value is None:
		return ""
	return str(value)


def result_to_csv_row(result: Dict[str, Any]) -> Dict[str, Any]:
	response = result.get("response") if isinstance(result.get("response"), dict) else {}
	return {
		"image_path": result.get("image_path", ""),
		"status": result.get("status", ""),
		"decision": response.get("decision", ""),
		"is_ai_asset": response.get("is_ai_asset", ""),
		"confidence": response.get("confidence", ""),
		"ai_evidence": compact_list(response.get("ai_evidence")),
		"normal_evidence": compact_list(response.get("normal_evidence")),
		"reason": response.get("reason", ""),
		"error": result.get("error", ""),
	}


def write_outputs(results: Sequence[Dict[str, Any]], out_dir: Path) -> None:
	out_dir.mkdir(parents=True, exist_ok=True)
	jsonl_path = out_dir / "ai_asset_ghc_results.jsonl"
	csv_path = out_dir / "ai_asset_ghc_results.csv"
	summary_path = out_dir / "summary.json"

	with open(jsonl_path, "w", encoding="utf-8") as handle:
		for result in results:
			handle.write(json.dumps(result, ensure_ascii=False) + "\n")

	with open(csv_path, "w", encoding="utf-8", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
		writer.writeheader()
		for result in results:
			writer.writerow(result_to_csv_row(result))

	summary = {"total": len(results), "ok": 0, "failed": 0, "missing_image": 0, "ai_asset": 0, "normal_asset": 0, "review": 0}
	for result in results:
		status = str(result.get("status", ""))
		if status in summary:
			summary[status] += 1
		response = result.get("response") if isinstance(result.get("response"), dict) else {}
		decision = str(response.get("decision", ""))
		if decision in summary:
			summary[decision] += 1
	with open(summary_path, "w", encoding="utf-8") as handle:
		json.dump(summary, handle, ensure_ascii=False, indent=2)


def progress_bar(done: int, total: int, width: int = 32) -> str:
	if total <= 0:
		return "[" + "." * width + "] 0/0"
	filled = min(width, int(width * done / total))
	bar = "#" * filled + "." * (width - filled)
	percent = 100 * done / total
	return f"[{bar}] {done}/{total} ({percent:5.1f}%)"


def write_partial_outputs(results: Sequence[Dict[str, Any]], out_dir: Path) -> None:
	ordered_results = sorted(results, key=lambda item: str(item.get("image_path", "")))
	write_outputs(ordered_results, out_dir)


def dry_run(paths: Sequence[str], out_dir: Path) -> int:
	results = []
	for image_path in paths:
		status = "dry_run_ok" if os.path.exists(image_path) else "missing_image"
		results.append({"image_path": image_path, "status": status, "error": "" if status == "dry_run_ok" else "image does not exist"})
	write_outputs(results, out_dir)
	return 0 if all(result["status"] == "dry_run_ok" for result in results) else 1


def run_batch(paths: Sequence[str], args: argparse.Namespace, out_dir: Path) -> List[Dict[str, Any]]:
	results: List[Dict[str, Any]] = []
	workers = max(args.workers, 1)
	save_every = max(args.save_every, 0)
	started = time.time()
	with ThreadPoolExecutor(max_workers=workers) as executor:
		future_to_path = {executor.submit(call_ghc_api, image_path, args): image_path for image_path in paths}
		for index, future in enumerate(as_completed(future_to_path), start=1):
			result = future.result()
			results.append(result)
			elapsed = max(time.time() - started, 0.001)
			rate = index / elapsed
			eta = (len(paths) - index) / rate if rate > 0 else 0
			status_counts = Counter(str(item.get("status", "")) for item in results)
			status_text = " ".join(f"{status}:{count}" for status, count in sorted(status_counts.items()) if status)
			print(
				f"\r{progress_bar(index, len(paths))} rate={rate:.2f}/s eta={eta/60:.1f}m {status_text}",
				end="",
				flush=True,
			)
			if save_every and index % save_every == 0:
				write_partial_outputs(results, out_dir)
				print(f"\ncheckpoint saved: {index} results -> {out_dir}", flush=True)
	print()
	results.sort(key=lambda item: str(item.get("image_path", "")))
	write_outputs(results, out_dir)
	print(f"finished {len(results)} images in {time.time() - started:.1f}s", flush=True)
	return results


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Batch classify images as AI assets through ghc-api.")
	parser.add_argument("image_paths", nargs="*", help="Image paths to classify. Defaults to the six requirement examples.")
	parser.add_argument("--paths-file", help="Text file with one image path per line.")
	parser.add_argument("--out-dir", default="jiaguyi_eval/ghc_ai_asset_report", help="Output directory for JSONL/CSV/summary files.")
	parser.add_argument("--ghc-api-url", default=os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL") or "http://localhost:8313", help="ghc-api base URL or /chat/completions URL.")
	parser.add_argument("--ghc-api-key-env", default="GHC_API_KEY", help="Environment variable containing ghc-api key.")
	parser.add_argument("--model", default=os.environ.get("GHC_API_MODEL", "opus-4.8"), help="Vision model name. Default: opus-4.8")
	parser.add_argument("--workers", type=int, default=50, help="Concurrent ghc-api requests. Default: 50")
	parser.add_argument("--save-every", type=int, default=500, help="Write checkpoint outputs every N completed images. Use 0 to disable. Default: 500")
	parser.add_argument("--timeout-sec", type=int, default=180, help="HTTP timeout for one request. Default: 180")
	parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature. Default: 0")
	parser.add_argument("--dry-run", action="store_true", help="Only validate image paths and write placeholder outputs; do not call ghc-api.")
	return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
	args = parse_args(argv)
	paths = read_image_paths(args)
	out_dir = Path(args.out_dir)
	if not paths:
		print("no image paths found", file=sys.stderr)
		return 2
	if args.dry_run:
		return dry_run(paths, out_dir)
	results = run_batch(paths, args, out_dir)
	return 1 if any(result.get("status") != "ok" for result in results) else 0


if __name__ == "__main__":
	raise SystemExit(main())

#!/usr/bin/env python3
"""Classify asset category and visible damage from captions and thumbnails."""

from __future__ import annotations

import argparse
import base64
import csv
import json
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


CSV_FIELDS = [
    "asset_id",
    "status",
    "name",
    "asset_category",
    "broken_or_damaged",
    "confidence",
    "damage_types",
    "reason",
    "caption",
    "thumbnail_url",
    "error",
]


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
    output = response_json.get("output")
    if isinstance(output, list):
        parts: List[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("output_text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "".join(parts)
    return ""


def extract_json_object(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return parsed


def build_prompt(record: Dict[str, str]) -> str:
    return (
        "你是3D资产视觉质检专家。请结合资产caption和缩略图，判断资产类别以及画面中是否存在破损。\n"
        "资产类别请选择最贴切的一类：character_humanoid, animal_creature, vehicle, weapon, "
        "furniture, electronics_machine, tool_equipment, architecture_building, architectural_component, "
        "household_object, clothing_accessory, food_plant, natural_object, terrain_environment, "
        "scene_diorama, sculpture_art, other。\n"
        "破损判定：yes表示能看到断裂、残缺、缺失主要部件、严重孔洞、碎片化、悬浮分离、扫描重建失败或明显网格崩坏；"
        "no表示可见主体完整。正常关节缝、设计上的开口、风格化低模、磨损纹理不算破损。"
        "单视角无法确认或caption与图片冲突时选uncertain。必须优先依据图片，不要仅凭caption中的broken等词。\n"
        "只返回JSON，不要Markdown，格式为：\n"
        "{\"asset_category\":\"...\",\"broken_or_damaged\":\"yes|no|uncertain\","
        "\"confidence\":0.0,\"damage_types\":[\"broken|missing_part|hole|fragmented|floating|scan_failure|mesh_corruption|other\"],"
        "\"reason\":\"简短中文理由，说明图片中的直接证据\"}\n"
        f"asset_id: {record['asset_id']}\n"
        f"name: {record['name']}\n"
        f"caption: {record['caption']}"
    )


def fetch_image_data_url(url: str, timeout_sec: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        content = response.read()
        mime_type = response.headers.get_content_type() or "image/jpeg"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def make_payload(record: Dict[str, str], model: str, image_data_url: str) -> Dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": build_prompt(record)},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    }


def make_caption_only_payload(record: Dict[str, str], model: str) -> Dict[str, Any]:
    prompt = (
        build_prompt(record)
        + "\n注意：图片因内容策略无法处理。请仅根据caption返回资产类别；"
        "broken_or_damaged必须返回uncertain，damage_types必须为空数组。"
    )
    return {"model": model, "input": prompt}


def post_record(record: Dict[str, str], args: argparse.Namespace) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(args.ghc_api_key_env, "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = ""
    for attempt in range(args.retries + 1):
        try:
            image_data_url = fetch_image_data_url(record["thumbnail_url"], args.timeout_sec)
            request = urllib.request.Request(
                normalize_responses_url(args.ghc_api_url),
                data=json.dumps(make_payload(record, args.model, image_data_url)).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=args.timeout_sec) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            result = extract_json_object(extract_response_text(response_json))
            return {**record, "status": "ok", "result": result, "error": ""}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1500:]
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code == 400 and "image processing blocked" in detail.lower():
                try:
                    fallback_request = urllib.request.Request(
                        normalize_responses_url(args.ghc_api_url),
                        data=json.dumps(make_caption_only_payload(record, args.model)).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(fallback_request, timeout=args.timeout_sec) as response:
                        response_json = json.loads(response.read().decode("utf-8"))
                    result = extract_json_object(extract_response_text(response_json))
                    result["broken_or_damaged"] = "uncertain"
                    result["damage_types"] = []
                    result["reason"] = "图片被内容策略阻止；仅根据caption分类，破损无法确认。"
                    return {
                        **record,
                        "status": "image_blocked_caption_only",
                        "result": result,
                        "error": last_error,
                    }
                except Exception as fallback_exc:
                    last_error += f"; caption fallback failed: {type(fallback_exc).__name__}: {fallback_exc}"
                break
            if exc.code < 500 and exc.code != 429:
                break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < args.retries:
            time.sleep(min(2**attempt, 8))
    return {**record, "status": "failed", "result": {}, "error": last_error}


def load_records(metadata_path: Path, caption_path: Path, limit: int) -> List[Dict[str, str]]:
    with metadata_path.open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    with caption_path.open(encoding="utf-8") as handle:
        captions = json.load(handle)

    records: List[Dict[str, str]] = []
    for asset_id, caption in list(captions.items())[:limit]:
        item = metadata.get(asset_id, {})
        records.append(
            {
                "asset_id": asset_id,
                "name": str(item.get("name", "")),
                "caption": str(caption),
                "thumbnail_url": str(item.get("thumbnail_url", "")),
            }
        )
    return records


def result_to_row(record: Dict[str, Any]) -> Dict[str, Any]:
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    damage_types = result.get("damage_types", [])
    return {
        "asset_id": record.get("asset_id", ""),
        "status": record.get("status", ""),
        "name": record.get("name", ""),
        "asset_category": result.get("asset_category", ""),
        "broken_or_damaged": result.get("broken_or_damaged", ""),
        "confidence": result.get("confidence", ""),
        "damage_types": "; ".join(str(value) for value in damage_types) if isinstance(damage_types, list) else str(damage_types),
        "reason": result.get("reason", ""),
        "caption": record.get("caption", ""),
        "thumbnail_url": record.get("thumbnail_url", ""),
        "error": record.get("error", ""),
    }


def write_outputs(records: Sequence[Dict[str, Any]], out_dir: Path, model: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda value: int(value.get("input_index", 0)))
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (out_dir / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(result_to_row(record) for record in ordered)

    categories: Counter[str] = Counter()
    damage: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    for record in ordered:
        statuses[str(record.get("status", ""))] += 1
        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        categories[str(result.get("asset_category", ""))] += 1
        damage[str(result.get("broken_or_damaged", ""))] += 1
    summary = {
        "model": model,
        "total": len(ordered),
        "status_counts": dict(statuses),
        "asset_category_counts": dict(categories),
        "broken_or_damaged_counts": dict(damage),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


def read_resumable_results(out_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = out_dir / "results.jsonl"
    if not path.exists():
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            asset_id = str(record.get("asset_id", ""))
            if asset_id and record.get("status") != "failed":
                results[asset_id] = record
    return results


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default="/Users/mlty/Downloads/metadata.json")
    parser.add_argument("--captions", default="/Users/mlty/Downloads/caption.json")
    parser.add_argument("--out-dir", default="data_filter/caption_image_ghc_report_100")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--ghc-api-url", default=os.environ.get("GHC_API_URL") or os.environ.get("GHC_API_BASE_URL") or "http://localhost:8313")
    parser.add_argument("--ghc-api-key-env", default="GHC_API_KEY")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--resume", action="store_true", help="Keep successful existing results and retry failures.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    records = load_records(Path(args.metadata), Path(args.captions), max(args.limit, 0))
    for index, record in enumerate(records):
        record["input_index"] = index
    existing = read_resumable_results(out_dir) if args.resume else {}
    results: List[Dict[str, Any]] = list(existing.values())
    pending = [record for record in records if record["asset_id"] not in existing]
    if existing:
        print(f"resume: keeping {len(existing)} completed results; pending={len(pending)}")
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        future_to_record = {executor.submit(post_record, record, args): record for record in pending}
        for completed, future in enumerate(as_completed(future_to_record), 1):
            result = future.result()
            results.append(result)
            print(f"\rcompleted {completed}/{len(pending)}", end="", flush=True)
    print()
    write_outputs(results, out_dir, args.model)
    successful_statuses = {"ok", "image_blocked_caption_only"}
    failed = sum(record.get("status") not in successful_statuses for record in results)
    print(f"finished in {time.time() - started:.1f}s; failed={failed}; output={args.out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)